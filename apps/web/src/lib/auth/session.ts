/**
 * The app's own session: an encrypted JWT (JWE, `dir` + A256GCM) keyed from FH_SESSION_SECRET.
 * It carries the Janua tokens server-side only; the browser sees an opaque httpOnly cookie.
 *
 * Lifetimes:
 * - idle: the cookie and the JWE expire SESSION_IDLE_SECONDS after the last write
 *   (sign-in or refresh-token rotation);
 * - absolute: no session outlives SESSION_ABSOLUTE_SECONDS after sign-in, whatever the rotation.
 */
import { EncryptJWT, jwtDecrypt } from "jose";
import { z } from "zod";

import { deriveKey } from "./keys";

export const SESSION_IDLE_SECONDS = 8 * 60 * 60;
export const SESSION_ABSOLUTE_SECONDS = 7 * 24 * 60 * 60;
/** Refresh when the access token has less than this many seconds left. */
export const ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60;

const sessionSchema = z.object({
  sub: z.string().min(1),
  email: z.string().optional(),
  name: z.string().optional(),
  accessToken: z.string().min(1),
  accessTokenExpiresAt: z.number().int(),
  refreshToken: z.string().min(1).optional(),
  idToken: z.string().min(1).optional(),
  authTime: z.number().int(),
});

export type SessionData = z.infer<typeof sessionSchema>;

const PROTECTED_HEADER = { alg: "dir", enc: "A256GCM", typ: "JWT", cty: "fh-session+v1" } as const;

export function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

/** Seconds until the JWE (and the cookie carrying it) expires. Never past the absolute cap. */
export function sessionTtlSeconds(data: SessionData, now: number = nowSeconds()): number {
  const absoluteEnd = data.authTime + SESSION_ABSOLUTE_SECONDS;
  return Math.max(0, Math.min(now + SESSION_IDLE_SECONDS, absoluteEnd) - now);
}

export async function encryptSession(
  data: SessionData,
  secret: string,
  now: number = nowSeconds(),
): Promise<string> {
  const parsed = sessionSchema.parse(data);
  const ttl = sessionTtlSeconds(parsed, now);
  if (ttl <= 0) throw new Error("session is past its absolute lifetime");
  return new EncryptJWT({ ...parsed })
    .setProtectedHeader(PROTECTED_HEADER)
    .setIssuedAt(now)
    .setNotBefore(now)
    .setExpirationTime(now + ttl)
    .encrypt(deriveKey(secret, "session"));
}

/**
 * Returns the session, or null for anything that is not a valid, unexpired session minted with
 * this secret: tampered, truncated, expired, wrong key, wrong algorithm or wrong shape.
 */
export async function decryptSession(
  token: string | undefined,
  secret: string,
  now: number = nowSeconds(),
): Promise<SessionData | null> {
  if (!token) return null;
  try {
    const { payload, protectedHeader } = await jwtDecrypt(token, deriveKey(secret, "session"), {
      keyManagementAlgorithms: ["dir"],
      contentEncryptionAlgorithms: ["A256GCM"],
      currentDate: new Date(now * 1000),
    });
    if (protectedHeader.cty !== PROTECTED_HEADER.cty) return null;
    const parsed = sessionSchema.safeParse(payload);
    if (!parsed.success) return null;
    if (parsed.data.authTime + SESSION_ABSOLUTE_SECONDS <= now) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

export function accessTokenNeedsRefresh(data: SessionData, now: number = nowSeconds()): boolean {
  return data.accessTokenExpiresAt - now <= ACCESS_TOKEN_REFRESH_SKEW_SECONDS;
}

export function accessTokenIsUsable(data: SessionData, now: number = nowSeconds()): boolean {
  return data.accessTokenExpiresAt > now;
}
