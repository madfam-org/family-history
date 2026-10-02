/**
 * The short-lived sign-in transaction: state, nonce, PKCE verifier and where to return.
 * Encrypted with its own key (see keys.ts) and kept in an httpOnly cookie for ten minutes.
 */
import { EncryptJWT, jwtDecrypt } from "jose";
import { z } from "zod";

import { defaultLocale, isLocale, type Locale } from "@/i18n/locales";

import { TRANSACTION_TTL_SECONDS } from "./cookies";
import { deriveKey } from "./keys";
import { nowSeconds } from "./session";

const transactionSchema = z.object({
  state: z.string().min(32),
  nonce: z.string().min(32),
  codeVerifier: z.string().min(43).max(128),
  returnTo: z.string().min(1),
});

export type OidcTransaction = z.infer<typeof transactionSchema>;

const PROTECTED_HEADER = { alg: "dir", enc: "A256GCM", typ: "JWT", cty: "fh-oidc-tx+v1" } as const;

export async function encryptTransaction(
  tx: OidcTransaction,
  secret: string,
  now: number = nowSeconds(),
): Promise<string> {
  const parsed = transactionSchema.parse(tx);
  return new EncryptJWT({ ...parsed })
    .setProtectedHeader(PROTECTED_HEADER)
    .setIssuedAt(now)
    .setExpirationTime(now + TRANSACTION_TTL_SECONDS)
    .encrypt(deriveKey(secret, "oidc-transaction"));
}

export async function decryptTransaction(
  token: string | undefined,
  secret: string,
  now: number = nowSeconds(),
): Promise<OidcTransaction | null> {
  if (!token) return null;
  try {
    const { payload, protectedHeader } = await jwtDecrypt(
      token,
      deriveKey(secret, "oidc-transaction"),
      {
        keyManagementAlgorithms: ["dir"],
        contentEncryptionAlgorithms: ["A256GCM"],
        currentDate: new Date(now * 1000),
      },
    );
    if (protectedHeader.cty !== PROTECTED_HEADER.cty) return null;
    const parsed = transactionSchema.safeParse(payload);
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

const RETURN_TO_PATTERN = /^\/(es|en)(\/[A-Za-z0-9\-._~%/]*)?(\?[A-Za-z0-9\-._~%&=+]*)?$/;

/**
 * Only same-origin, locale-prefixed app paths are accepted as a post-sign-in destination.
 * Anything else (absolute URLs, protocol-relative `//`, backslashes, odd characters) falls back
 * to the default home, so the callback can never become an open redirect.
 */
export function safeReturnTo(value: string | null | undefined, fallbackLocale: Locale = defaultLocale): string {
  const fallback = `/${fallbackLocale}`;
  if (!value || value.length > 512) return fallback;
  if (value.includes("//") || value.includes("\\")) return fallback;
  return RETURN_TO_PATTERN.test(value) ? value : fallback;
}

export function localeOfPath(path: string): Locale {
  const segment = path.split("/")[1];
  return isLocale(segment) ? segment : defaultLocale;
}
