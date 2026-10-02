import { CompactEncrypt } from "jose";
import { describe, expect, it } from "vitest";

import {
  applyWritesToCookieHeader,
  clearChunked,
  cookieName,
  MAX_CHUNK_LENGTH,
  readChunked,
  writeChunked,
} from "@/lib/auth/cookies";
import { deriveKey } from "@/lib/auth/keys";
import {
  accessTokenNeedsRefresh,
  decryptSession,
  encryptSession,
  SESSION_ABSOLUTE_SECONDS,
  SESSION_IDLE_SECONDS,
  sessionTtlSeconds,
  type SessionData,
} from "@/lib/auth/session";
import { decryptTransaction, encryptTransaction, safeReturnTo } from "@/lib/auth/transaction";

const SECRET = "test-session-secret-that-is-long-enough-0123456789";
const NOW = 1_790_000_000;

const session: SessionData = {
  sub: "user-synthetic-1",
  email: "ana.synthetic@example.test",
  name: "Ana Prueba",
  accessToken: "access-token-synthetic",
  accessTokenExpiresAt: NOW + 900,
  refreshToken: "refresh-token-synthetic",
  idToken: "id.token.synthetic",
  authTime: NOW,
};

describe("session encryption", () => {
  it("round-trips", async () => {
    const token = await encryptSession(session, SECRET, NOW);
    expect(token.split(".")).toHaveLength(5);
    expect(token).not.toContain("access-token-synthetic");
    await expect(decryptSession(token, SECRET, NOW + 10)).resolves.toEqual(session);
  });

  it("rejects tampering anywhere in the token", async () => {
    const token = await encryptSession(session, SECRET, NOW);
    const parts = token.split(".");
    for (const index of [0, 2, 3, 4]) {
      const altered = [...parts];
      const part = altered[index] ?? "";
      altered[index] = `${part.slice(0, -2)}${part.endsWith("AA") ? "BB" : "AA"}`;
      await expect(decryptSession(altered.join("."), SECRET, NOW)).resolves.toBeNull();
    }
  });

  it("rejects another secret, garbage and absent cookies", async () => {
    const token = await encryptSession(session, SECRET, NOW);
    await expect(decryptSession(token, `${SECRET}-other`, NOW)).resolves.toBeNull();
    await expect(decryptSession("not-a-jwe", SECRET, NOW)).resolves.toBeNull();
    await expect(decryptSession(undefined, SECRET, NOW)).resolves.toBeNull();
  });

  it("expires after the idle window and never outlives the absolute window", async () => {
    const token = await encryptSession(session, SECRET, NOW);
    await expect(decryptSession(token, SECRET, NOW + SESSION_IDLE_SECONDS + 1)).resolves.toBeNull();
    const old = { ...session, authTime: NOW - SESSION_ABSOLUTE_SECONDS + 60 };
    expect(sessionTtlSeconds(old, NOW)).toBe(60);
    await expect(encryptSession({ ...session, authTime: NOW - SESSION_ABSOLUTE_SECONDS }, SECRET, NOW)).rejects.toThrow();
  });

  it("does not accept a transaction cookie as a session (separate keys)", async () => {
    const tx = await encryptTransaction(
      { state: "s".repeat(43), nonce: "n".repeat(43), codeVerifier: "v".repeat(43), returnTo: "/es" },
      SECRET,
      NOW,
    );
    await expect(decryptSession(tx, SECRET, NOW)).resolves.toBeNull();
    await expect(decryptTransaction(tx, SECRET, NOW)).resolves.toMatchObject({ returnTo: "/es" });
  });

  it("rejects a well-formed JWE with the wrong content type", async () => {
    const forged = await new CompactEncrypt(new TextEncoder().encode(JSON.stringify({ ...session, exp: NOW + 60 })))
      .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
      .encrypt(deriveKey(SECRET, "session"));
    await expect(decryptSession(forged, SECRET, NOW)).resolves.toBeNull();
  });

  it("flags access tokens close to expiry for refresh", () => {
    expect(accessTokenNeedsRefresh(session, NOW)).toBe(false);
    expect(accessTokenNeedsRefresh(session, NOW + 850)).toBe(true);
  });
});

describe("cookie chunking", () => {
  it("splits, joins and clears stale chunks", () => {
    const value = "x".repeat(MAX_CHUNK_LENGTH * 2 + 10);
    const writes = writeChunked("fh_session", value, 100, [{ name: "fh_session.3", value: "old" }]);
    expect(writes.map((write) => write.name)).toEqual(["fh_session.0", "fh_session.1", "fh_session.2", "fh_session.3"]);
    expect(writes.at(-1)).toMatchObject({ maxAge: 0 });
    const jar = writes.filter((write) => write.maxAge > 0);
    expect(readChunked("fh_session", jar)).toBe(value);
    expect(clearChunked("fh_session", jar)).toHaveLength(3);
  });

  it("reads a gap as absent and rebuilds request cookie headers", () => {
    expect(readChunked("fh_session", [{ name: "fh_session.1", value: "x" }])).toBeUndefined();
    const header = applyWritesToCookieHeader(
      [
        { name: "other", value: "1" },
        { name: "fh_session.0", value: "old" },
      ],
      [{ name: "fh_session.0", value: "new", maxAge: 10 }],
    );
    expect(header).toBe("other=1; fh_session.0=new");
  });

  it("uses __Host- names when cookies are Secure", () => {
    expect(cookieName("fh_session", { FH_ENV: "production" })).toBe("__Host-fh_session");
    expect(cookieName("fh_session", { FH_ENV: "local" })).toBe("fh_session");
  });
});

describe("safeReturnTo", () => {
  it("accepts locale-prefixed app paths only", () => {
    expect(safeReturnTo("/es/familias/abc?q=Ana")).toBe("/es/familias/abc?q=Ana");
    expect(safeReturnTo("/en")).toBe("/en");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil", "/es//evil", "/fr", "javascript:x", ""]) {
      expect(safeReturnTo(bad)).toBe("/es");
    }
  });
});
