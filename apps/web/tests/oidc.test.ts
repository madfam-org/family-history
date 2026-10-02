import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type JWK } from "jose";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";

import { refreshIfNeeded } from "@/lib/auth/lifecycle";
import {
  buildAuthorizationUrl,
  buildEndSessionUrl,
  clearDiscoveryCache,
  discover,
  OidcError,
  parseDiscovery,
  verifyIdToken,
  type OidcMetadata,
} from "@/lib/auth/oidc";
import type { SessionData } from "@/lib/auth/session";

const ISSUER = "https://auth.example.test";
const CLIENT_ID = "family-history-web";

const document = {
  issuer: ISSUER,
  authorization_endpoint: `${ISSUER}/oauth/authorize`,
  token_endpoint: `${ISSUER}/oauth/token`,
  jwks_uri: `${ISSUER}/.well-known/jwks.json`,
  end_session_endpoint: `${ISSUER}/oauth/logout`,
  registration_endpoint: "https://attacker.example/register",
  code_challenge_methods_supported: ["plain", "S256"],
  token_endpoint_auth_methods_supported: ["client_secret_basic", "client_secret_post"],
  id_token_signing_alg_values_supported: ["RS256"],
};

let privateKey: CryptoKey;
let jwks: ReturnType<typeof createLocalJWKSet>;
let metadata: OidcMetadata;

beforeAll(async () => {
  const pair = await generateKeyPair("RS256", { extractable: true });
  privateKey = pair.privateKey;
  const publicJwk: JWK = { ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256", use: "sig" };
  jwks = createLocalJWKSet({ keys: [publicJwk] });
  metadata = parseDiscovery(document, ISSUER);
});

function idToken(claims: Record<string, unknown> = {}, options: { audience?: string | string[]; issuer?: string } = {}) {
  return new SignJWT({ nonce: "nonce-1", email: "ana@example.test", ...claims })
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(options.issuer ?? ISSUER)
    .setAudience(options.audience ?? CLIENT_ID)
    .setSubject("user-1")
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(privateKey);
}

describe("discovery validation", () => {
  it("never exposes the registration endpoint and always uses S256", () => {
    expect(Object.values(metadata)).not.toContain("https://attacker.example/register");
    const url = new URL(
      buildAuthorizationUrl(metadata, {
        clientId: CLIENT_ID,
        redirectUri: "https://fh-app.madfam.io/auth/callback",
        state: "state-1",
        nonce: "nonce-1",
        codeChallenge: "challenge",
        prompt: "select_account",
      }),
    );
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("prompt")).toBe("select_account");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("scope")).toContain("openid");
  });

  it("rejects an issuer mismatch", () => {
    expect(() => parseDiscovery({ ...document, issuer: "https://evil.example" }, ISSUER)).toThrow(OidcError);
  });

  it("rejects issuers that only offer plain PKCE or no RS256", () => {
    expect(() => parseDiscovery({ ...document, code_challenge_methods_supported: ["plain"] }, ISSUER)).toThrow(
      /S256/,
    );
    expect(() => parseDiscovery({ ...document, id_token_signing_alg_values_supported: ["HS256"] }, ISSUER)).toThrow(
      /RS256/,
    );
  });

  it("rejects plain-HTTP endpoints for a public issuer", () => {
    expect(() => parseDiscovery({ ...document, token_endpoint: "http://auth.example.test/token" }, ISSUER)).toThrow(
      /https/,
    );
  });

  it("caches the fetched document and fails visibly when unreachable", async () => {
    clearDiscoveryCache();
    let calls = 0;
    const fetchImpl = (async () => {
      calls += 1;
      return Response.json(document);
    }) as typeof fetch;
    await discover(ISSUER, fetchImpl);
    await discover(ISSUER, fetchImpl);
    expect(calls).toBe(1);
    clearDiscoveryCache();
    const failing = (async () => {
      throw new Error("down");
    }) as typeof fetch;
    await expect(discover(ISSUER, failing)).rejects.toMatchObject({ code: "discovery_failed" });
  });

  it("builds RP-initiated logout URLs with the ID token hint", () => {
    const url = new URL(
      buildEndSessionUrl(metadata, {
        clientId: CLIENT_ID,
        postLogoutRedirectUri: "https://fh.madfam.io/",
        idTokenHint: "hint",
      }) ?? "",
    );
    expect(url.origin + url.pathname).toBe(`${ISSUER}/oauth/logout`);
    expect(url.searchParams.get("id_token_hint")).toBe("hint");
    expect(buildEndSessionUrl({ ...metadata, endSessionEndpoint: undefined }, { clientId: CLIENT_ID, postLogoutRedirectUri: "x" })).toBeUndefined();
  });
});

describe("ID token verification", () => {
  it("accepts a valid RS256 token with the right nonce", async () => {
    const claims = await verifyIdToken(await idToken(), { metadata, clientId: CLIENT_ID, nonce: "nonce-1", keys: jwks });
    expect(claims.sub).toBe("user-1");
  });

  it("rejects a wrong nonce, audience or issuer", async () => {
    const options = { metadata, clientId: CLIENT_ID, keys: jwks };
    await expect(verifyIdToken(await idToken(), { ...options, nonce: "other" })).rejects.toMatchObject({
      code: "id_token_invalid",
    });
    await expect(verifyIdToken(await idToken({}, { audience: "someone-else" }), options)).rejects.toThrow(OidcError);
    await expect(verifyIdToken(await idToken({}, { issuer: "https://evil.example" }), options)).rejects.toThrow(
      OidcError,
    );
  });

  it("requires azp when there are several audiences", async () => {
    const options = { metadata, clientId: CLIENT_ID, keys: jwks };
    await expect(verifyIdToken(await idToken({}, { audience: [CLIENT_ID, "other"] }), options)).rejects.toThrow(
      /azp/,
    );
    await expect(
      verifyIdToken(await idToken({ azp: CLIENT_ID }, { audience: [CLIENT_ID, "other"] }), options),
    ).resolves.toMatchObject({ sub: "user-1" });
  });

  it("rejects HS256 tokens even when signed with a known secret", async () => {
    const hs = await new SignJWT({ nonce: "nonce-1" })
      .setProtectedHeader({ alg: "HS256" })
      .setIssuer(ISSUER)
      .setAudience(CLIENT_ID)
      .setSubject("user-1")
      .setIssuedAt()
      .setExpirationTime("5m")
      .sign(new TextEncoder().encode("client-secret-used-as-hmac-key-0123456789"));
    await expect(verifyIdToken(hs, { metadata, clientId: CLIENT_ID, keys: jwks })).rejects.toThrow(OidcError);
  });
});

describe("refresh-token rotation", () => {
  const client = { issuer: ISSUER, clientId: CLIENT_ID, clientSecret: "synthetic-secret" };
  const now = 1_790_000_000;
  const base: SessionData = {
    sub: "user-1",
    accessToken: "old-access",
    accessTokenExpiresAt: now + 10,
    refreshToken: "refresh-a",
    authTime: now - 100,
  };

  beforeEach(() => clearDiscoveryCache());

  it("rotates once for concurrent requests and keeps the new refresh token", async () => {
    let calls = 0;
    const fetchImpl = (async () => {
      calls += 1;
      return Response.json({ access_token: "new-access", token_type: "Bearer", expires_in: 900, refresh_token: "refresh-b" });
    }) as typeof fetch;
    const deps = { client, metadata, fetchImpl, now };
    const [first, second] = await Promise.all([refreshIfNeeded(base, deps), refreshIfNeeded(base, deps)]);
    expect(calls).toBe(1);
    expect(first).toEqual(second);
    expect(first).toMatchObject({ kind: "refreshed", session: { accessToken: "new-access", refreshToken: "refresh-b" } });
    // A late request still carrying the old token reuses the rotation instead of replaying it.
    await expect(refreshIfNeeded(base, deps)).resolves.toMatchObject({ kind: "refreshed" });
    expect(calls).toBe(1);
  });

  it("ends the session when the issuer rejects the refresh token", async () => {
    const fetchImpl = (async () => Response.json({ error: "invalid_grant" }, { status: 400 })) as typeof fetch;
    await expect(
      refreshIfNeeded({ ...base, refreshToken: "refresh-dead" }, { client, metadata, fetchImpl, now }),
    ).resolves.toEqual({ kind: "ended" });
  });

  it("keeps the session on transient issuer failures", async () => {
    const fetchImpl = (async () => new Response("bad gateway", { status: 502 })) as typeof fetch;
    await expect(
      refreshIfNeeded({ ...base, refreshToken: "refresh-flaky" }, { client, metadata, fetchImpl, now }),
    ).resolves.toEqual({ kind: "unchanged" });
  });

  it("does nothing while the access token is fresh", async () => {
    const fetchImpl = (async () => {
      throw new Error("must not be called");
    }) as typeof fetch;
    await expect(
      refreshIfNeeded({ ...base, accessTokenExpiresAt: now + 600 }, { client, metadata, fetchImpl, now }),
    ).resolves.toEqual({ kind: "unchanged" });
  });
});
