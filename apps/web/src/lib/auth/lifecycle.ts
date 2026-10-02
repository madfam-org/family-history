/**
 * Session lifecycle: building a session from a token response, and refresh-token rotation.
 * Rotation runs in the proxy (the only place a page request can rewrite cookies) and is
 * single-flight per refresh token, so parallel requests never replay a rotated token.
 */
import type { OidcClientConfig } from "@/lib/env";

import {
  OidcError,
  refreshTokens,
  verifyIdToken,
  type FetchLike,
  type IdTokenClaims,
  type OidcMetadata,
  type TokenResponse,
} from "./oidc";
import { accessTokenNeedsRefresh, nowSeconds, type SessionData } from "./session";

export function sessionFromTokens(
  tokens: TokenResponse,
  claims: IdTokenClaims,
  now: number = nowSeconds(),
  previous?: SessionData,
): SessionData {
  return {
    sub: claims.sub,
    email: typeof claims.email === "string" ? claims.email : previous?.email,
    name: typeof claims.name === "string" ? claims.name : previous?.name,
    accessToken: tokens.access_token,
    accessTokenExpiresAt: now + tokens.expires_in,
    // Rotation: a new refresh token replaces the old one; otherwise the old one stays valid.
    refreshToken: tokens.refresh_token ?? previous?.refreshToken,
    idToken: tokens.id_token ?? previous?.idToken,
    authTime: previous?.authTime ?? now,
  };
}

export type RefreshOutcome =
  | { kind: "unchanged" }
  | { kind: "refreshed"; session: SessionData }
  | { kind: "ended" };

export interface RefreshDeps {
  client: OidcClientConfig;
  metadata: OidcMetadata;
  fetchImpl?: FetchLike;
  verify?: typeof verifyIdToken;
  now?: number;
}

const inflight = new Map<string, Promise<RefreshOutcome>>();
/**
 * Recently rotated refresh tokens. A request that left the browser before the rotated cookie
 * arrived still carries the old token; it reuses the rotation result instead of replaying the
 * old token, which the issuer would treat as reuse.
 */
const recentRotations = new Map<string, { outcome: RefreshOutcome; expiresAt: number }>();
const RECENT_ROTATION_MS = 30_000;

function rememberRotation(key: string, outcome: RefreshOutcome): void {
  const now = Date.now();
  for (const [token, entry] of recentRotations) {
    if (entry.expiresAt <= now) recentRotations.delete(token);
  }
  if (outcome.kind === "refreshed") recentRotations.set(key, { outcome, expiresAt: now + RECENT_ROTATION_MS });
}

async function rotate(session: SessionData, deps: RefreshDeps, now: number): Promise<RefreshOutcome> {
  if (!session.refreshToken) return { kind: "ended" };
  try {
    const tokens = await refreshTokens(deps.metadata, deps.client, session.refreshToken, deps.fetchImpl);
    let claims: IdTokenClaims = { sub: session.sub, email: session.email, name: session.name };
    if (tokens.id_token) {
      claims = await (deps.verify ?? verifyIdToken)(tokens.id_token, {
        metadata: deps.metadata,
        clientId: deps.client.clientId,
      });
      // A refreshed ID token must describe the same person (OIDC Core §12.2).
      if (claims.sub !== session.sub) return { kind: "ended" };
    }
    return { kind: "refreshed", session: sessionFromTokens(tokens, claims, now, session) };
  } catch (error) {
    if (error instanceof OidcError && (error.code === "refresh_rejected" || error.code === "id_token_invalid")) {
      return { kind: "ended" };
    }
    // Transient (issuer unreachable or 5xx): keep the session; pages treat an expired access
    // token as signed out, so nothing runs on stale credentials.
    return { kind: "unchanged" };
  }
}

export async function refreshIfNeeded(session: SessionData, deps: RefreshDeps): Promise<RefreshOutcome> {
  const now = deps.now ?? nowSeconds();
  if (!accessTokenNeedsRefresh(session, now)) return { kind: "unchanged" };
  if (!session.refreshToken) {
    return session.accessTokenExpiresAt > now ? { kind: "unchanged" } : { kind: "ended" };
  }
  const key = session.refreshToken;
  const recent = recentRotations.get(key);
  if (recent && recent.expiresAt > Date.now()) return recent.outcome;
  const existing = inflight.get(key);
  if (existing) return existing;
  const pending = rotate(session, deps, now)
    .then((outcome) => {
      rememberRotation(key, outcome);
      return outcome;
    })
    .finally(() => inflight.delete(key));
  inflight.set(key, pending);
  return pending;
}
