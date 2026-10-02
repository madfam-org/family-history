/**
 * Self-contained OpenID Connect client for Janua (ADR 0001: no private packages).
 *
 * - Discovery from `<issuer>/.well-known/openid-configuration`, validated: the document's issuer
 *   must equal the configured issuer, and endpoints must be HTTPS (plain HTTP only for a
 *   localhost issuer in local development).
 * - `registration_endpoint` is never read: this client is registered out of band.
 * - PKCE is always S256; an issuer that advertises methods without S256 is rejected, and `plain`
 *   is never used.
 * - Confidential client: the token exchange runs server-side with the client secret.
 * - ID tokens: RS256 only, via JWKS, with issuer, audience (= client id), azp and nonce checks.
 */
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";
import { z } from "zod";

import type { OidcClientConfig } from "@/lib/env";

import { safeEqual } from "./pkce";

export type FetchLike = typeof fetch;

const HTTP_TIMEOUT_MS = 10_000;
const DISCOVERY_TTL_MS = 60 * 60 * 1000;

export class OidcError extends Error {
  constructor(
    readonly code:
      | "discovery_failed"
      | "discovery_invalid"
      | "token_exchange_failed"
      | "token_response_invalid"
      | "id_token_invalid"
      | "refresh_failed"
      | "refresh_rejected",
    message: string,
  ) {
    super(message);
    this.name = "OidcError";
  }
}

const discoverySchema = z.object({
  issuer: z.string().min(1),
  authorization_endpoint: z.string().url(),
  token_endpoint: z.string().url(),
  jwks_uri: z.string().url(),
  end_session_endpoint: z.string().url().optional(),
  code_challenge_methods_supported: z.array(z.string()).optional(),
  token_endpoint_auth_methods_supported: z.array(z.string()).optional(),
  id_token_signing_alg_values_supported: z.array(z.string()).optional(),
});

export interface OidcMetadata {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  jwksUri: string;
  endSessionEndpoint: string | undefined;
  tokenEndpointAuthMethod: "client_secret_basic" | "client_secret_post";
}

function isLocalhost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]" || hostname.endsWith(".localhost");
}

function assertTrustedEndpoint(value: string, issuer: URL, field: string): string {
  const url = new URL(value);
  const allowHttp = issuer.protocol === "http:" && isLocalhost(issuer.hostname) && isLocalhost(url.hostname);
  if (url.protocol !== "https:" && !allowHttp) {
    throw new OidcError("discovery_invalid", `${field} must use https`);
  }
  return url.toString();
}

/** Validates a discovery document against the configured issuer. Pure; exported for tests. */
export function parseDiscovery(document: unknown, configuredIssuer: string): OidcMetadata {
  const parsed = discoverySchema.safeParse(document);
  if (!parsed.success) throw new OidcError("discovery_invalid", "discovery document is malformed");
  const doc = parsed.data;
  if (doc.issuer.replace(/\/+$/, "") !== configuredIssuer.replace(/\/+$/, "")) {
    throw new OidcError("discovery_invalid", "discovery issuer does not match the configured issuer");
  }
  const issuerUrl = new URL(configuredIssuer);
  if (doc.code_challenge_methods_supported && !doc.code_challenge_methods_supported.includes("S256")) {
    throw new OidcError("discovery_invalid", "issuer does not support PKCE S256");
  }
  if (
    doc.id_token_signing_alg_values_supported &&
    !doc.id_token_signing_alg_values_supported.includes("RS256")
  ) {
    throw new OidcError("discovery_invalid", "issuer does not sign ID tokens with RS256");
  }
  const methods = doc.token_endpoint_auth_methods_supported;
  let tokenEndpointAuthMethod: OidcMetadata["tokenEndpointAuthMethod"];
  if (!methods || methods.includes("client_secret_basic")) tokenEndpointAuthMethod = "client_secret_basic";
  else if (methods.includes("client_secret_post")) tokenEndpointAuthMethod = "client_secret_post";
  else throw new OidcError("discovery_invalid", "issuer supports no client-secret auth method");

  return {
    issuer: doc.issuer,
    authorizationEndpoint: assertTrustedEndpoint(doc.authorization_endpoint, issuerUrl, "authorization_endpoint"),
    tokenEndpoint: assertTrustedEndpoint(doc.token_endpoint, issuerUrl, "token_endpoint"),
    jwksUri: assertTrustedEndpoint(doc.jwks_uri, issuerUrl, "jwks_uri"),
    endSessionEndpoint: doc.end_session_endpoint
      ? assertTrustedEndpoint(doc.end_session_endpoint, issuerUrl, "end_session_endpoint")
      : undefined,
    tokenEndpointAuthMethod,
  };
}

const discoveryCache = new Map<string, { value: OidcMetadata; expiresAt: number }>();

export async function discover(issuer: string, fetchImpl: FetchLike = fetch): Promise<OidcMetadata> {
  const cached = discoveryCache.get(issuer);
  if (cached && cached.expiresAt > Date.now()) return cached.value;
  let response: Response;
  try {
    response = await fetchImpl(`${issuer.replace(/\/+$/, "")}/.well-known/openid-configuration`, {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch {
    throw new OidcError("discovery_failed", "issuer discovery is unreachable");
  }
  if (!response.ok) throw new OidcError("discovery_failed", `discovery returned ${response.status}`);
  const value = parseDiscovery(await response.json().catch(() => null), issuer);
  discoveryCache.set(issuer, { value, expiresAt: Date.now() + DISCOVERY_TTL_MS });
  return value;
}

export function clearDiscoveryCache(): void {
  discoveryCache.clear();
}

export type PromptMode = "select_account" | "login";

export function parsePrompt(value: string | null | undefined): PromptMode | undefined {
  return value === "select_account" || value === "login" ? value : undefined;
}

export interface AuthorizationRequest {
  clientId: string;
  redirectUri: string;
  state: string;
  nonce: string;
  codeChallenge: string;
  prompt?: PromptMode | undefined;
  uiLocales?: string | undefined;
}

/** Sign-in scopes plus the API scopes the app uses (janua.client.yaml: fh:read, fh:write). */
export const OIDC_SCOPES = "openid profile email offline_access fh:read fh:write";

export function buildAuthorizationUrl(metadata: OidcMetadata, request: AuthorizationRequest): string {
  const url = new URL(metadata.authorizationEndpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", request.clientId);
  url.searchParams.set("redirect_uri", request.redirectUri);
  url.searchParams.set("scope", OIDC_SCOPES);
  url.searchParams.set("state", request.state);
  url.searchParams.set("nonce", request.nonce);
  url.searchParams.set("code_challenge", request.codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  if (request.prompt) url.searchParams.set("prompt", request.prompt);
  if (request.uiLocales) url.searchParams.set("ui_locales", request.uiLocales);
  return url.toString();
}

const tokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string().refine((value) => value.toLowerCase() === "bearer"),
  expires_in: z.coerce.number().int().positive(),
  refresh_token: z.string().min(1).optional(),
  id_token: z.string().min(1).optional(),
});

export type TokenResponse = z.infer<typeof tokenResponseSchema>;

/** RFC 6749 §2.3.1: id and secret are form-urlencoded before Basic encoding. */
function basicAuthorization(client: OidcClientConfig): string {
  const encode = (value: string) => encodeURIComponent(value).replace(/%20/g, "+");
  return `Basic ${Buffer.from(`${encode(client.clientId)}:${encode(client.clientSecret)}`).toString("base64")}`;
}

async function tokenRequest(
  metadata: OidcMetadata,
  client: OidcClientConfig,
  params: Record<string, string>,
  fetchImpl: FetchLike,
  failure: "token_exchange_failed" | "refresh_failed",
): Promise<{ status: number; body: unknown }> {
  const body = new URLSearchParams(params);
  const headers: Record<string, string> = {
    "content-type": "application/x-www-form-urlencoded",
    accept: "application/json",
  };
  if (metadata.tokenEndpointAuthMethod === "client_secret_basic") {
    headers.authorization = basicAuthorization(client);
  } else {
    body.set("client_id", client.clientId);
    body.set("client_secret", client.clientSecret);
  }
  try {
    const response = await fetchImpl(metadata.tokenEndpoint, {
      method: "POST",
      headers,
      body: body.toString(),
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
      cache: "no-store",
    });
    return { status: response.status, body: await response.json().catch(() => null) };
  } catch {
    throw new OidcError(failure, "token endpoint is unreachable");
  }
}

export async function exchangeCode(
  metadata: OidcMetadata,
  client: OidcClientConfig,
  input: { code: string; codeVerifier: string; redirectUri: string },
  fetchImpl: FetchLike = fetch,
): Promise<TokenResponse & { id_token: string }> {
  const { status, body } = await tokenRequest(
    metadata,
    client,
    {
      grant_type: "authorization_code",
      code: input.code,
      code_verifier: input.codeVerifier,
      redirect_uri: input.redirectUri,
    },
    fetchImpl,
    "token_exchange_failed",
  );
  if (status < 200 || status >= 300) {
    throw new OidcError("token_exchange_failed", `token endpoint returned ${status}`);
  }
  const parsed = tokenResponseSchema.safeParse(body);
  if (!parsed.success || !parsed.data.id_token) {
    throw new OidcError("token_response_invalid", "token response is missing required fields");
  }
  return { ...parsed.data, id_token: parsed.data.id_token };
}

/**
 * Refresh-token grant. A 400/401 means the grant is dead (revoked, reused or expired) and the
 * session must end; anything else is a transient failure.
 */
export async function refreshTokens(
  metadata: OidcMetadata,
  client: OidcClientConfig,
  refreshToken: string,
  fetchImpl: FetchLike = fetch,
): Promise<TokenResponse> {
  const { status, body } = await tokenRequest(
    metadata,
    client,
    { grant_type: "refresh_token", refresh_token: refreshToken },
    fetchImpl,
    "refresh_failed",
  );
  if (status === 400 || status === 401) throw new OidcError("refresh_rejected", "refresh token rejected");
  if (status < 200 || status >= 300) throw new OidcError("refresh_failed", `token endpoint returned ${status}`);
  const parsed = tokenResponseSchema.safeParse(body);
  if (!parsed.success) throw new OidcError("token_response_invalid", "refresh response is malformed");
  return parsed.data;
}

const jwksCache = new Map<string, JWTVerifyGetKey>();

export function remoteJwks(metadata: OidcMetadata): JWTVerifyGetKey {
  let jwks = jwksCache.get(metadata.jwksUri);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(metadata.jwksUri), { timeoutDuration: HTTP_TIMEOUT_MS });
    jwksCache.set(metadata.jwksUri, jwks);
  }
  return jwks;
}

export interface IdTokenClaims extends JWTPayload {
  sub: string;
  email?: string;
  name?: string;
  nonce?: string;
}

/**
 * Verifies an ID token: RS256 signature from the issuer's JWKS, `iss`, `aud` containing the
 * client id (and `azp` equal to it when there are several audiences), and the nonce when one
 * was sent. Refreshed ID tokens are verified without a nonce.
 */
export async function verifyIdToken(
  idToken: string,
  options: { metadata: OidcMetadata; clientId: string; nonce?: string; keys?: JWTVerifyGetKey },
): Promise<IdTokenClaims> {
  let payload: JWTPayload;
  try {
    ({ payload } = await jwtVerify(idToken, options.keys ?? remoteJwks(options.metadata), {
      algorithms: ["RS256"],
      issuer: options.metadata.issuer,
      audience: options.clientId,
      requiredClaims: ["sub", "iat", "exp"],
      clockTolerance: 30,
    }));
  } catch {
    throw new OidcError("id_token_invalid", "ID token failed verification");
  }
  if (Array.isArray(payload.aud) && payload.aud.length > 1 && payload.azp !== options.clientId) {
    throw new OidcError("id_token_invalid", "ID token azp does not match the client");
  }
  if (options.nonce !== undefined) {
    if (typeof payload.nonce !== "string" || !safeEqual(payload.nonce, options.nonce)) {
      throw new OidcError("id_token_invalid", "ID token nonce does not match");
    }
  }
  if (typeof payload.sub !== "string" || payload.sub.length === 0) {
    throw new OidcError("id_token_invalid", "ID token has no subject");
  }
  return payload as IdTokenClaims;
}

export function buildEndSessionUrl(
  metadata: OidcMetadata,
  input: { clientId: string; postLogoutRedirectUri: string; idTokenHint?: string | undefined; uiLocales?: string },
): string | undefined {
  if (!metadata.endSessionEndpoint) return undefined;
  const url = new URL(metadata.endSessionEndpoint);
  url.searchParams.set("client_id", input.clientId);
  url.searchParams.set("post_logout_redirect_uri", input.postLogoutRedirectUri);
  if (input.idTokenHint) url.searchParams.set("id_token_hint", input.idTokenHint);
  if (input.uiLocales) url.searchParams.set("ui_locales", input.uiLocales);
  return url.toString();
}
