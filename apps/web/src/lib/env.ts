/**
 * Runtime configuration, read on every call so that one image serves every environment.
 * Variable names follow the contract in docs/ARCHITECTURE.md §Environment. Values never live
 * in the repository, and nothing here is exposed to the browser.
 */

export type Env = Readonly<Record<string, string | undefined>>;

export type DeployEnv = "local" | "test" | "staging" | "production";

const DEFAULT_LANDING_HOST = "localhost:3000";
const DEFAULT_APP_HOST = "app.localhost:3000";

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/** Hosts are compared lower-case, without a trailing dot. Ports are kept: they are part of a host. */
export function normalizeHost(host: string | null | undefined): string {
  return (host ?? "").trim().toLowerCase().replace(/\.$/, "");
}

export function deployEnv(env: Env = process.env): DeployEnv {
  const value = clean(env.FH_ENV);
  if (value === "local" || value === "test" || value === "staging" || value === "production") {
    return value;
  }
  // An unset FH_ENV is treated as production: the strictest behaviour is the default.
  return "production";
}

export interface HostConfig {
  landingHost: string;
  appHost: string;
}

export function hostConfig(env: Env = process.env): HostConfig {
  return {
    landingHost: normalizeHost(clean(env.FH_PUBLIC_LANDING_HOST) ?? DEFAULT_LANDING_HOST),
    appHost: normalizeHost(clean(env.FH_PUBLIC_APP_HOST) ?? DEFAULT_APP_HOST),
  };
}

/** `https` everywhere except local development, where the hosts are plain-HTTP localhost names. */
export function publicScheme(env: Env = process.env): "http" | "https" {
  return deployEnv(env) === "local" ? "http" : "https";
}

export function landingOrigin(env: Env = process.env): string {
  return `${publicScheme(env)}://${hostConfig(env).landingHost}`;
}

export function appOrigin(env: Env = process.env): string {
  return `${publicScheme(env)}://${hostConfig(env).appHost}`;
}

/** Indexing is opt-in: only the exact string `true` enables it (ADR 0001, working hosts stay noindex). */
export function isIndexable(env: Env = process.env): boolean {
  return env.FH_INDEXABLE === "true";
}

export function apiInternalUrl(env: Env = process.env): string | undefined {
  const value = clean(env.FH_API_INTERNAL_URL);
  return value?.replace(/\/+$/, "");
}

export interface PlausibleConfig {
  /** The site domain reported to Plausible (`data-domain`). */
  domain: string;
  /** Origin of the self-hosted Plausible instance that serves the script and receives events. */
  origin: string;
}

/**
 * Analytics only through the self-hosted Plausible. Both the reported domain and the instance
 * origin must be set, and the origin must be HTTPS; otherwise analytics stays off.
 */
export function plausibleConfig(env: Env = process.env): PlausibleConfig | undefined {
  const domain = clean(env.FH_PLAUSIBLE_DOMAIN);
  const rawOrigin = clean(env.FH_PLAUSIBLE_ORIGIN);
  if (!domain || !rawOrigin) return undefined;
  try {
    const url = new URL(rawOrigin);
    if (url.protocol !== "https:") return undefined;
    return { domain, origin: url.origin };
  } catch {
    return undefined;
  }
}

export interface OidcClientConfig {
  issuer: string;
  clientId: string;
  clientSecret: string;
}

/** Returns undefined when sign-in is not configured; callers show a visible configuration error. */
export function oidcClientConfig(env: Env = process.env): OidcClientConfig | undefined {
  const issuer = clean(env.AUTH_JANUA_ISSUER);
  const clientId = clean(env.AUTH_JANUA_CLIENT_ID);
  const clientSecret = clean(env.AUTH_JANUA_CLIENT_SECRET);
  if (!issuer || !clientId || !clientSecret) return undefined;
  return { issuer: issuer.replace(/\/+$/, ""), clientId, clientSecret };
}

/** The exact redirect URI registered with Janua: `https://<app host>/auth/callback`. */
export function oidcRedirectUri(env: Env = process.env): string {
  return `${appOrigin(env)}/auth/callback`;
}

export const SESSION_SECRET_MIN_BYTES = 32;

/** FH_SESSION_SECRET, never the Janua client secret (ruling R42). Undefined when too short. */
export function sessionSecret(env: Env = process.env): string | undefined {
  const value = env.FH_SESSION_SECRET;
  if (!value || Buffer.byteLength(value, "utf8") < SESSION_SECRET_MIN_BYTES) return undefined;
  return value;
}

export interface WaitlistConfig {
  enabled: boolean;
  avisoVersion: string | undefined;
}

export function waitlistConfig(env: Env = process.env): WaitlistConfig {
  return {
    enabled: env.FH_WAITLIST_ENABLED === "true",
    avisoVersion: clean(env.FH_AVISO_VERSION),
  };
}
