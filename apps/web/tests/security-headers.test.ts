import { describe, expect, it } from "vitest";

import { baseSecurityHeaders, buildCsp } from "@/lib/security/headers";

const prod = {
  FH_ENV: "production",
  FH_PUBLIC_LANDING_HOST: "fh.madfam.io",
  FH_PUBLIC_APP_HOST: "fh-app.madfam.io",
  AUTH_JANUA_ISSUER: "https://auth.madfam.io",
  AUTH_JANUA_CLIENT_ID: "family-history-web",
  AUTH_JANUA_CLIENT_SECRET: "synthetic",
};

describe("Content-Security-Policy", () => {
  it("is nonce-based with strict-dynamic and no unsafe-eval in production", () => {
    const csp = buildCsp("abc123", prod, false);
    expect(csp).toContain("script-src 'self' 'nonce-abc123' 'strict-dynamic'");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("allows the sign-out redirect chain (issuer, then back to the app) as form targets", () => {
    expect(buildCsp("n", prod, false)).toContain("form-action 'self' https://auth.madfam.io;");
  });

  it("adds the self-hosted Plausible origin only when fully configured over HTTPS", () => {
    expect(buildCsp("n", prod, false)).not.toContain("plausible");
    const withPlausible = { ...prod, FH_PLAUSIBLE_DOMAIN: "fh.madfam.io", FH_PLAUSIBLE_ORIGIN: "https://plausible.example.test" };
    expect(buildCsp("n", withPlausible, false)).toMatch(/connect-src 'self' https:\/\/plausible\.example\.test/);
    const insecure = { ...withPlausible, FH_PLAUSIBLE_ORIGIN: "http://plausible.example.test" };
    expect(buildCsp("n", insecure, false)).not.toContain("plausible");
  });

  it("permits eval only in development", () => {
    expect(buildCsp("n", { FH_ENV: "local" }, true)).toContain("'unsafe-eval'");
    expect(buildCsp("n", { FH_ENV: "local" }, true)).not.toContain("upgrade-insecure-requests");
  });
});

describe("base headers", () => {
  it("set nosniff, frame denial and HSTS on HTTPS deployments", () => {
    const headers = baseSecurityHeaders(prod);
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Strict-Transport-Security"]).toContain("max-age=");
    expect(baseSecurityHeaders({ FH_ENV: "local" })["Strict-Transport-Security"]).toBeUndefined();
  });
});
