import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } from "jose";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";

import { readChunked } from "@/lib/auth/cookies";
import { handleCallback, handleSignOut, handleStart } from "@/lib/auth/handlers";
import { clearDiscoveryCache, verifyIdToken } from "@/lib/auth/oidc";
import { decryptSession } from "@/lib/auth/session";

const ISSUER = "https://auth.example.test";
const env = {
  FH_ENV: "production",
  FH_PUBLIC_LANDING_HOST: "fh.example.test",
  FH_PUBLIC_APP_HOST: "fh-app.example.test",
  AUTH_JANUA_ISSUER: ISSUER,
  AUTH_JANUA_CLIENT_ID: "family-history-web",
  AUTH_JANUA_CLIENT_SECRET: "synthetic-client-secret",
  FH_SESSION_SECRET: "synthetic-session-secret-0123456789-abcdefghij",
};

let privateKey: CryptoKey;
let keys: ReturnType<typeof createLocalJWKSet>;
const tokenRequests: URLSearchParams[] = [];
const tokenAuthHeaders: (string | null)[] = [];
let issuedNonce = "";

const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  if (url.endsWith("/.well-known/openid-configuration")) {
    return Response.json({
      issuer: ISSUER,
      authorization_endpoint: `${ISSUER}/authorize`,
      token_endpoint: `${ISSUER}/token`,
      jwks_uri: `${ISSUER}/jwks`,
      end_session_endpoint: `${ISSUER}/logout`,
      code_challenge_methods_supported: ["S256"],
    });
  }
  if (url === `${ISSUER}/token`) {
    const body = new URLSearchParams(String(init?.body));
    tokenRequests.push(body);
    tokenAuthHeaders.push(new Headers(init?.headers).get("authorization"));
    const idToken = await new SignJWT({ nonce: issuedNonce, email: "ana@example.test", name: "Ana Prueba" })
      .setProtectedHeader({ alg: "RS256", kid: "k1" })
      .setIssuer(ISSUER)
      .setAudience(env.AUTH_JANUA_CLIENT_ID)
      .setSubject("user-1")
      .setIssuedAt()
      .setExpirationTime("5m")
      .sign(privateKey);
    return Response.json({
      access_token: "access-1",
      token_type: "Bearer",
      expires_in: 900,
      refresh_token: "refresh-1",
      id_token: idToken,
    });
  }
  return new Response("not found", { status: 404 });
}) as typeof fetch;

const verify: typeof verifyIdToken = (token, options) => verifyIdToken(token, { ...options, keys });

function setCookies(response: Response): { name: string; value: string; raw: string }[] {
  return response.headers.getSetCookie().map((raw) => {
    const [pair = ""] = raw.split(";");
    const index = pair.indexOf("=");
    return { name: pair.slice(0, index), value: pair.slice(index + 1), raw };
  });
}

beforeAll(async () => {
  const pair = await generateKeyPair("RS256", { extractable: true });
  privateKey = pair.privateKey;
  keys = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256" }] });
});

beforeEach(() => {
  clearDiscoveryCache();
  tokenRequests.length = 0;
  tokenAuthHeaders.length = 0;
});

async function startFlow(query = "return_to=%2Fes%2Fajustes&prompt=login") {
  const response = await handleStart(new Request(`https://fh-app.example.test/auth/start?${query}`), { env, fetchImpl });
  const location = new URL(response.headers.get("location") ?? "");
  issuedNonce = location.searchParams.get("nonce") ?? "";
  const tx = setCookies(response).find((cookie) => cookie.name === "__Host-fh_oidc_tx");
  return { response, location, tx };
}

describe("sign-in flow", () => {
  it("starts with PKCE S256, state, nonce, prompt and an encrypted transaction cookie", async () => {
    const { response, location, tx } = await startFlow();
    expect(response.status).toBe(303);
    expect(location.origin).toBe(ISSUER);
    expect(location.searchParams.get("redirect_uri")).toBe("https://fh-app.example.test/auth/callback");
    expect(location.searchParams.get("code_challenge_method")).toBe("S256");
    expect(location.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(location.searchParams.get("state")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(location.searchParams.get("prompt")).toBe("login");
    expect(location.searchParams.get("scope")?.split(" ")).toEqual(
      expect.arrayContaining(["openid", "offline_access", "fh:read", "fh:write"]),
    );
    expect(tx?.raw).toContain("HttpOnly");
    expect(tx?.raw).toContain("Secure");
    expect(tx?.raw).toContain("SameSite=Lax");
  });

  it("completes the callback into an encrypted session and returns to the requested page", async () => {
    const { location, tx } = await startFlow();
    const state = location.searchParams.get("state");
    const callback = await handleCallback(
      new Request(`https://fh-app.example.test/auth/callback?code=code-1&state=${state}`, {
        headers: { cookie: `${tx?.name}=${tx?.value}` },
      }),
      { env, fetchImpl, verify },
    );
    expect(callback.headers.get("location")).toBe("https://fh-app.example.test/es/ajustes");
    const request = tokenRequests[0];
    expect(request?.get("grant_type")).toBe("authorization_code");
    expect(request?.get("code_verifier")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(request?.get("client_secret")).toBeNull();
    expect(tokenAuthHeaders[0]).toMatch(/^Basic /);

    const cookies = setCookies(callback);
    expect(cookies.find((cookie) => cookie.name === "__Host-fh_oidc_tx")?.raw).toContain("Max-Age=0");
    const raw = readChunked("__Host-fh_session", cookies.filter((cookie) => cookie.value));
    const session = await decryptSession(raw, env.FH_SESSION_SECRET);
    expect(session).toMatchObject({ sub: "user-1", accessToken: "access-1", refreshToken: "refresh-1" });
  });

  it("rejects a state mismatch without calling the token endpoint", async () => {
    const { tx } = await startFlow();
    const callback = await handleCallback(
      new Request("https://fh-app.example.test/auth/callback?code=code-1&state=forged", {
        headers: { cookie: `${tx?.name}=${tx?.value}` },
      }),
      { env, fetchImpl, verify },
    );
    expect(callback.headers.get("location")).toContain("/es/entrar?error=invalid");
    expect(tokenRequests).toHaveLength(0);
  });

  it("treats a missing transaction cookie as expired", async () => {
    const callback = await handleCallback(new Request("https://fh-app.example.test/auth/callback?code=c&state=s"), {
      env,
      fetchImpl,
      verify,
    });
    expect(callback.headers.get("location")).toBe("https://fh-app.example.test/es/entrar?error=expired");
  });

  it("reports a nonce mismatch as an invalid sign-in", async () => {
    const { location, tx } = await startFlow();
    issuedNonce = "a-different-nonce";
    const callback = await handleCallback(
      new Request(`https://fh-app.example.test/auth/callback?code=c&state=${location.searchParams.get("state")}`, {
        headers: { cookie: `${tx?.name}=${tx?.value}` },
      }),
      { env, fetchImpl, verify },
    );
    expect(callback.headers.get("location")).toContain("error=invalid");
  });

  it("says sign-in is not configured instead of failing silently", async () => {
    const response = await handleStart(new Request("https://fh-app.example.test/auth/start"), {
      env: { ...env, AUTH_JANUA_CLIENT_SECRET: "" },
      fetchImpl,
    });
    expect(response.headers.get("location")).toBe("https://fh-app.example.test/es/entrar?error=not_configured");
  });

  it("refuses a session secret shorter than 32 bytes", async () => {
    const response = await handleStart(new Request("https://fh-app.example.test/auth/start"), {
      env: { ...env, FH_SESSION_SECRET: "too-short" },
      fetchImpl,
    });
    expect(response.headers.get("location")).toContain("error=not_configured");
  });
});

describe("sign-out", () => {
  it("clears the session and redirects to the issuer's end-session endpoint", async () => {
    const response = await handleSignOut(
      new Request("https://fh-app.example.test/auth/signout", {
        method: "POST",
        headers: { origin: "https://fh-app.example.test", cookie: "__Host-fh_session.0=abc" },
        body: new URLSearchParams({ locale: "en" }),
      }),
      { env, fetchImpl },
    );
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.origin + location.pathname).toBe(`${ISSUER}/logout`);
    expect(location.searchParams.get("post_logout_redirect_uri")).toBe("https://fh-app.example.test/");
    expect(setCookies(response)[0]?.raw).toContain("Max-Age=0");
  });

  it("rejects cross-site sign-out posts", async () => {
    const response = await handleSignOut(
      new Request("https://fh-app.example.test/auth/signout", {
        method: "POST",
        headers: { origin: "https://evil.example" },
      }),
      { env, fetchImpl },
    );
    expect(response.status).toBe(403);
  });
});

describe("sign-out without an end-session endpoint", () => {
  it("clears locally and lands on the sign-in page, not at the issuer", async () => {
    const noLogout = (async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/.well-known/openid-configuration")) {
        return Response.json({
          issuer: ISSUER,
          authorization_endpoint: `${ISSUER}/authorize`,
          token_endpoint: `${ISSUER}/token`,
          jwks_uri: `${ISSUER}/jwks`,
        });
      }
      return fetchImpl(input, init);
    }) as typeof fetch;
    clearDiscoveryCache();
    const response = await handleSignOut(
      new Request("https://fh-app.example.test/auth/signout", {
        method: "POST",
        headers: { origin: "https://fh-app.example.test", cookie: "__Host-fh_session.0=abc; __Host-fh_session.1=def" },
        body: new URLSearchParams({ locale: "es" }),
      }),
      { env, fetchImpl: noLogout },
    );
    expect(response.headers.get("location")).toBe("https://fh-app.example.test/es/entrar?signed_out=1");
    expect(setCookies(response).map((cookie) => cookie.name)).toEqual(["__Host-fh_session.0", "__Host-fh_session.1"]);
  });
});
