import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  codeChallengeS256,
  createCodeVerifier,
  createNonce,
  createState,
  isValidCodeVerifier,
  randomToken,
  safeEqual,
} from "@/lib/auth/pkce";

describe("PKCE", () => {
  it("matches the RFC 7636 appendix B example", () => {
    expect(codeChallengeS256("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });

  it("creates verifiers that satisfy RFC 7636 and hash to base64url SHA-256", () => {
    const verifier = createCodeVerifier();
    expect(isValidCodeVerifier(verifier)).toBe(true);
    expect(verifier).toHaveLength(43);
    const expected = createHash("sha256").update(verifier).digest("base64url");
    expect(codeChallengeS256(verifier)).toBe(expected);
    expect(codeChallengeS256(verifier)).not.toMatch(/[+/=]/);
  });

  it("rejects verifiers that are too short or use reserved characters", () => {
    expect(() => codeChallengeS256("short")).toThrow();
    expect(() => codeChallengeS256(`${"a".repeat(42)}+`)).toThrow();
    expect(isValidCodeVerifier("a".repeat(129))).toBe(false);
  });
});

describe("state and nonce", () => {
  it("are unique, URL-safe and carry 256 bits", () => {
    const states = new Set(Array.from({ length: 200 }, () => createState()));
    expect(states.size).toBe(200);
    const nonce = createNonce();
    expect(nonce).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("refuses weak random tokens", () => {
    expect(() => randomToken(8)).toThrow(RangeError);
  });

  it("compares in constant time and rejects empty values", () => {
    const value = createState();
    expect(safeEqual(value, value)).toBe(true);
    expect(safeEqual(value, createState())).toBe(false);
    expect(safeEqual(value, value.slice(1))).toBe(false);
    expect(safeEqual("", "")).toBe(false);
  });
});
