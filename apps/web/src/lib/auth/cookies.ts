/**
 * Cookie names, attributes and chunking for the app's own encrypted cookies.
 *
 * Browsers cap a cookie at about 4 KB. An encrypted session that carries an access token, a
 * refresh token and an ID token can pass that, so values are split into numbered chunks
 * (`<name>.0`, `<name>.1`, ...) and joined back on read.
 */
import { deployEnv, type Env } from "@/lib/env";

export const SESSION_COOKIE_BASE = "fh_session";
export const TRANSACTION_COOKIE_BASE = "fh_oidc_tx";
export const TRANSACTION_TTL_SECONDS = 10 * 60;
export const MAX_CHUNK_LENGTH = 3800;
/** A session is a few KB; anything needing more chunks than this is treated as garbage. */
export const MAX_CHUNKS = 8;

export interface CookieRecord {
  name: string;
  value: string;
}

export interface CookieWrite {
  name: string;
  value: string;
  maxAge: number;
}

export interface CookieAttributes {
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
}

/**
 * Secure everywhere except plain-HTTP local development. Secure cookies take the `__Host-`
 * prefix, which pins them to this exact host and path `/` with no Domain attribute.
 */
export function cookieSecure(env: Env = process.env): boolean {
  return deployEnv(env) !== "local";
}

export function cookieName(base: string, env: Env = process.env): string {
  return cookieSecure(env) ? `__Host-${base}` : base;
}

export function cookieAttributes(env: Env = process.env): CookieAttributes {
  return { httpOnly: true, secure: cookieSecure(env), sameSite: "lax", path: "/" };
}

function chunkName(name: string, index: number): string {
  return `${name}.${index}`;
}

/** Reads a chunked value. Missing chunk 0, a gap or too many chunks all read as absent. */
export function readChunked(name: string, cookies: readonly CookieRecord[]): string | undefined {
  const byName = new Map(cookies.map((cookie) => [cookie.name, cookie.value]));
  const parts: string[] = [];
  for (let index = 0; index < MAX_CHUNKS; index += 1) {
    const part = byName.get(chunkName(name, index));
    if (part === undefined) break;
    parts.push(part);
  }
  if (parts.length === 0) return undefined;
  if (byName.has(chunkName(name, MAX_CHUNKS))) return undefined;
  return parts.join("");
}

/**
 * Writes for a chunked value, plus deletions (maxAge 0) for stale chunks left over from a
 * longer previous value.
 */
export function writeChunked(
  name: string,
  value: string,
  maxAge: number,
  existing: readonly CookieRecord[],
): CookieWrite[] {
  const writes: CookieWrite[] = [];
  const count = Math.ceil(value.length / MAX_CHUNK_LENGTH);
  if (count > MAX_CHUNKS) throw new Error("cookie value too large");
  for (let index = 0; index < count; index += 1) {
    writes.push({
      name: chunkName(name, index),
      value: value.slice(index * MAX_CHUNK_LENGTH, (index + 1) * MAX_CHUNK_LENGTH),
      maxAge,
    });
  }
  return [...writes, ...clearStaleChunks(name, count, existing)];
}

/** Deletions for every chunk of `name` from index `from` on. */
export function clearStaleChunks(
  name: string,
  from: number,
  existing: readonly CookieRecord[],
): CookieWrite[] {
  const prefix = `${name}.`;
  return existing
    .filter((cookie) => cookie.name.startsWith(prefix))
    .filter((cookie) => {
      const index = Number(cookie.name.slice(prefix.length));
      return Number.isInteger(index) && index >= from;
    })
    .map((cookie) => ({ name: cookie.name, value: "", maxAge: 0 }));
}

export function clearChunked(name: string, existing: readonly CookieRecord[]): CookieWrite[] {
  return clearStaleChunks(name, 0, existing);
}

/** Re-serialises a request `Cookie` header after applying writes, so the render sees them. */
export function applyWritesToCookieHeader(
  existing: readonly CookieRecord[],
  writes: readonly CookieWrite[],
): string {
  const jar = new Map(existing.map((cookie) => [cookie.name, cookie.value]));
  for (const write of writes) {
    if (write.maxAge <= 0) jar.delete(write.name);
    else jar.set(write.name, write.value);
  }
  return [...jar.entries()].map(([name, value]) => `${name}=${value}`).join("; ");
}
