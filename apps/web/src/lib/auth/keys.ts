/**
 * Encryption keys for the app's own cookies, derived from FH_SESSION_SECRET with HKDF-SHA-256.
 * Each cookie purpose gets its own key, so a value minted for one purpose never decrypts as
 * another. The Janua client secret is never used here (ruling R42).
 */
import { hkdfSync } from "node:crypto";

export type KeyPurpose = "session" | "oidc-transaction";

const INFO: Readonly<Record<KeyPurpose, string>> = {
  session: "family-history/web/session/v1",
  "oidc-transaction": "family-history/web/oidc-transaction/v1",
};

export function deriveKey(secret: string, purpose: KeyPurpose): Uint8Array {
  if (!secret) throw new Error("FH_SESSION_SECRET is required");
  const derived = hkdfSync("sha256", Buffer.from(secret, "utf8"), Buffer.alloc(0), INFO[purpose], 32);
  return new Uint8Array(derived);
}
