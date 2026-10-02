/**
 * Route-handler logic for /auth/start, /auth/callback and /auth/signout. Framework-free (plain
 * Request in, plain Response out) so the whole flow is unit-testable.
 */
import { appOrigin, oidcClientConfig, oidcRedirectUri, sessionSecret, type Env } from "@/lib/env";

import {
  clearChunked,
  cookieAttributes,
  cookieName,
  readChunked,
  SESSION_COOKIE_BASE,
  TRANSACTION_COOKIE_BASE,
  TRANSACTION_TTL_SECONDS,
  writeChunked,
  type CookieRecord,
  type CookieWrite,
} from "./cookies";
import { sessionFromTokens } from "./lifecycle";
import {
  buildAuthorizationUrl,
  buildEndSessionUrl,
  discover,
  exchangeCode,
  OidcError,
  parsePrompt,
  verifyIdToken,
  type FetchLike,
} from "./oidc";
import { codeChallengeS256, createCodeVerifier, createNonce, createState, safeEqual } from "./pkce";
import { decryptSession, encryptSession, nowSeconds, sessionTtlSeconds } from "./session";
import { decryptTransaction, encryptTransaction, localeOfPath, safeReturnTo } from "./transaction";

export type SignInError = "not_configured" | "denied" | "expired" | "invalid" | "unavailable";

export interface HandlerDeps {
  env?: Env;
  fetchImpl?: FetchLike;
  verify?: typeof verifyIdToken;
}

function parseCookieHeader(header: string | null): CookieRecord[] {
  if (!header) return [];
  return header
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const index = part.indexOf("=");
      const name = index === -1 ? part : part.slice(0, index);
      const value = index === -1 ? "" : part.slice(index + 1);
      return { name, value };
    });
}

function serializeCookie(write: CookieWrite, env: Env): string {
  const attributes = cookieAttributes(env);
  const parts = [`${write.name}=${write.value}`, `Path=${attributes.path}`, `Max-Age=${write.maxAge}`, "HttpOnly", "SameSite=Lax"];
  if (attributes.secure) parts.push("Secure");
  return parts.join("; ");
}

function redirectResponse(location: string, writes: readonly CookieWrite[], env: Env, status = 303): Response {
  const headers = new Headers({ Location: location, "Cache-Control": "no-store" });
  for (const write of writes) headers.append("Set-Cookie", serializeCookie(write, env));
  return new Response(null, { status, headers });
}

function signInErrorUrl(env: Env, locale: string, error: SignInError, returnTo?: string): string {
  const params = new URLSearchParams({ error });
  if (returnTo) params.set("return_to", returnTo);
  return `${appOrigin(env)}/${locale}/entrar?${params.toString()}`;
}

function errorCodeFor(error: unknown): SignInError {
  if (error instanceof OidcError) {
    if (error.code === "discovery_failed" || error.code === "token_exchange_failed") return "unavailable";
    return "invalid";
  }
  return "unavailable";
}

/** GET /auth/start?return_to=/es/...&prompt=select_account|login */
export async function handleStart(request: Request, deps: HandlerDeps = {}): Promise<Response> {
  const env = deps.env ?? process.env;
  const url = new URL(request.url);
  const returnTo = safeReturnTo(url.searchParams.get("return_to"));
  const locale = localeOfPath(returnTo);
  const client = oidcClientConfig(env);
  const secret = sessionSecret(env);
  if (!client || !secret) return redirectResponse(signInErrorUrl(env, locale, "not_configured"), [], env);

  try {
    const metadata = await discover(client.issuer, deps.fetchImpl);
    const state = createState();
    const nonce = createNonce();
    const codeVerifier = createCodeVerifier();
    const authorizationUrl = buildAuthorizationUrl(metadata, {
      clientId: client.clientId,
      redirectUri: oidcRedirectUri(env),
      state,
      nonce,
      codeChallenge: codeChallengeS256(codeVerifier),
      prompt: parsePrompt(url.searchParams.get("prompt")),
      uiLocales: locale === "es" ? "es-MX es en" : "en es",
    });
    const tx = await encryptTransaction({ state, nonce, codeVerifier, returnTo }, secret);
    const txWrite = { name: cookieName(TRANSACTION_COOKIE_BASE, env), value: tx, maxAge: TRANSACTION_TTL_SECONDS };
    return redirectResponse(authorizationUrl, [txWrite], env);
  } catch (error) {
    return redirectResponse(signInErrorUrl(env, locale, errorCodeFor(error), returnTo), [], env);
  }
}

/** GET /auth/callback?code=...&state=... (the exact redirect URI registered with Janua). */
export async function handleCallback(request: Request, deps: HandlerDeps = {}): Promise<Response> {
  const env = deps.env ?? process.env;
  const url = new URL(request.url);
  const cookies = parseCookieHeader(request.headers.get("cookie"));
  const txName = cookieName(TRANSACTION_COOKIE_BASE, env);
  const clearTx: CookieWrite = { name: txName, value: "", maxAge: 0 };
  const client = oidcClientConfig(env);
  const secret = sessionSecret(env);
  if (!client || !secret) return redirectResponse(signInErrorUrl(env, "es", "not_configured"), [clearTx], env);

  const tx = await decryptTransaction(cookies.find((cookie) => cookie.name === txName)?.value, secret);
  if (!tx) return redirectResponse(signInErrorUrl(env, "es", "expired"), [clearTx], env);
  const locale = localeOfPath(tx.returnTo);

  const returnedState = url.searchParams.get("state") ?? "";
  if (!safeEqual(returnedState, tx.state)) {
    return redirectResponse(signInErrorUrl(env, locale, "invalid", tx.returnTo), [clearTx], env);
  }
  if (url.searchParams.has("error")) {
    return redirectResponse(signInErrorUrl(env, locale, "denied", tx.returnTo), [clearTx], env);
  }
  const code = url.searchParams.get("code");
  if (!code) return redirectResponse(signInErrorUrl(env, locale, "invalid", tx.returnTo), [clearTx], env);

  try {
    const metadata = await discover(client.issuer, deps.fetchImpl);
    const tokens = await exchangeCode(
      metadata,
      client,
      { code, codeVerifier: tx.codeVerifier, redirectUri: oidcRedirectUri(env) },
      deps.fetchImpl,
    );
    const claims = await (deps.verify ?? verifyIdToken)(tokens.id_token, {
      metadata,
      clientId: client.clientId,
      nonce: tx.nonce,
    });
    const now = nowSeconds();
    const session = sessionFromTokens(tokens, claims, now);
    const value = await encryptSession(session, secret, now);
    const sessionName = cookieName(SESSION_COOKIE_BASE, env);
    const writes = writeChunked(sessionName, value, sessionTtlSeconds(session, now), cookies);
    return redirectResponse(`${appOrigin(env)}${tx.returnTo}`, [clearTx, ...writes], env);
  } catch (error) {
    return redirectResponse(signInErrorUrl(env, locale, errorCodeFor(error), tx.returnTo), [clearTx], env);
  }
}

/** True for a POST sent by a page of the app itself (Origin, else Sec-Fetch-Site). */
export function isSameOriginPost(request: Request, env: Env = process.env): boolean {
  const origin = request.headers.get("origin");
  if (origin) return origin === appOrigin(env);
  return request.headers.get("sec-fetch-site") === "same-origin";
}

/**
 * POST /auth/signout: clears the app session, then RP-initiated logout at the issuer's
 * end-session endpoint when it has one; otherwise the local clear is the whole sign-out.
 */
export async function handleSignOut(request: Request, deps: HandlerDeps = {}): Promise<Response> {
  const env = deps.env ?? process.env;
  if (!isSameOriginPost(request, env)) {
    return new Response("Forbidden", { status: 403, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
  const cookies = parseCookieHeader(request.headers.get("cookie"));
  const sessionName = cookieName(SESSION_COOKIE_BASE, env);
  const writes = clearChunked(sessionName, cookies);
  const form = await request.formData().catch(() => null);
  const locale = form?.get("locale") === "en" ? "en" : "es";
  // A signed-out person lands on the sign-in page, never straight back at the issuer, so an
  // issuer-side session cannot silently sign them in again.
  const signedOutUrl = `${appOrigin(env)}/${locale}/entrar?signed_out=1`;

  const client = oidcClientConfig(env);
  const secret = sessionSecret(env);
  if (!client || !secret) return redirectResponse(signedOutUrl, writes, env);
  const session = await decryptSession(readChunked(sessionName, cookies), secret);
  try {
    const metadata = await discover(client.issuer, deps.fetchImpl);
    const endSession = buildEndSessionUrl(metadata, {
      clientId: client.clientId,
      // Registered exactly in janua.client.yaml (post_logout_redirect_uris).
      postLogoutRedirectUri: `${appOrigin(env)}/`,
      idTokenHint: session?.idToken,
      uiLocales: locale === "es" ? "es-MX es en" : "en es",
    });
    return redirectResponse(endSession ?? signedOutUrl, writes, env);
  } catch {
    return redirectResponse(signedOutUrl, writes, env);
  }
}
