/**
 * PKCE (RFC 7636, S256 only), `state` and `nonce` helpers. `plain` is never offered, whatever
 * the issuer's discovery document says.
 */
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

/** 32 random bytes → 43 base64url characters (256 bits of entropy). */
export function randomToken(byteLength = 32): string {
  if (!Number.isInteger(byteLength) || byteLength < 16) {
    throw new RangeError("random tokens need at least 16 bytes of entropy");
  }
  return randomBytes(byteLength).toString("base64url");
}

const VERIFIER_PATTERN = /^[A-Za-z0-9\-._~]{43,128}$/;

export function isValidCodeVerifier(verifier: string): boolean {
  return VERIFIER_PATTERN.test(verifier);
}

export function createCodeVerifier(): string {
  return randomToken(32);
}

export function codeChallengeS256(verifier: string): string {
  if (!isValidCodeVerifier(verifier)) {
    throw new Error("code_verifier must be 43-128 unreserved characters (RFC 7636 §4.1)");
  }
  return createHash("sha256").update(verifier, "ascii").digest("base64url");
}

export function createState(): string {
  return randomToken(32);
}

export function createNonce(): string {
  return randomToken(32);
}

/** Constant-time string comparison for state and nonce checks. */
export function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a, "utf8");
  const right = Buffer.from(b, "utf8");
  if (left.length !== right.length || left.length === 0) return false;
  return timingSafeEqual(left, right);
}
