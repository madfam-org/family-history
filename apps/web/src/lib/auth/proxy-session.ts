/**
 * Session maintenance for app-host page requests, run from the proxy: decrypts the session
 * cookie, rotates the refresh token when the access token is about to expire, and returns the
 * cookie writes for both the response (browser) and the forwarded request (this render).
 */
import { oidcClientConfig, sessionSecret, type Env } from "@/lib/env";

import {
  clearChunked,
  cookieName,
  readChunked,
  SESSION_COOKIE_BASE,
  writeChunked,
  type CookieRecord,
  type CookieWrite,
} from "./cookies";
import { refreshIfNeeded, type RefreshDeps } from "./lifecycle";
import { discover } from "./oidc";
import { decryptSession, encryptSession, nowSeconds, sessionTtlSeconds } from "./session";

export async function maintainSession(
  cookies: readonly CookieRecord[],
  env: Env = process.env,
  deps: Partial<Pick<RefreshDeps, "fetchImpl" | "verify" | "metadata">> = {},
): Promise<CookieWrite[]> {
  const secret = sessionSecret(env);
  const client = oidcClientConfig(env);
  if (!secret || !client) return [];
  const name = cookieName(SESSION_COOKIE_BASE, env);
  const raw = readChunked(name, cookies);
  if (!raw) return [];

  const now = nowSeconds();
  const session = await decryptSession(raw, secret, now);
  if (!session) return clearChunked(name, cookies);

  let metadata = deps.metadata;
  if (!metadata) {
    try {
      metadata = await discover(client.issuer, deps.fetchImpl);
    } catch {
      return [];
    }
  }
  const outcome = await refreshIfNeeded(session, { client, metadata, now, ...deps });
  if (outcome.kind === "unchanged") return [];
  if (outcome.kind === "ended") return clearChunked(name, cookies);
  const value = await encryptSession(outcome.session, secret, now);
  return writeChunked(name, value, sessionTtlSeconds(outcome.session, now), cookies);
}
