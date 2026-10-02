/**
 * Security headers, set by the proxy on every response.
 *
 * The CSP is nonce-based with 'strict-dynamic': only scripts carrying this request's nonce (the
 * Next.js runtime and, when configured, the Plausible loader) run. JSON-LD blocks are data, not
 * scripts, and are not executed. Fonts are self-hosted by next/font,
 * so no Google Fonts origin is needed. The self-hosted Plausible origin is added only when
 * analytics is configured; the Janua issuer is a form-action target only, for the sign-out
 * redirect chain.
 */
import { randomBytes } from "node:crypto";

import { deployEnv, oidcClientConfig, plausibleConfig, publicScheme, type Env } from "@/lib/env";

export function createNonce(): string {
  return randomBytes(16).toString("base64");
}

export function buildCsp(nonce: string, env: Env = process.env, isDev = process.env.NODE_ENV === "development"): string {
  const plausible = plausibleConfig(env);
  const issuer = oidcClientConfig(env)?.issuer;
  let issuerOrigin: string | undefined;
  if (issuer) {
    try {
      issuerOrigin = new URL(issuer).origin;
    } catch {
      issuerOrigin = undefined;
    }
  }

  const scriptSrc = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  if (plausible) scriptSrc.push(plausible.origin);
  if (isDev) scriptSrc.push("'unsafe-eval'");

  const connectSrc = ["'self'"];
  if (plausible) connectSrc.push(plausible.origin);

  // Sign-out is a form POST that redirects to the issuer's end-session endpoint and back to
  // the app; browsers apply form-action to every hop of that chain.
  const formAction = ["'self'"];
  if (issuerOrigin) formAction.push(issuerOrigin);

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSrc.join(" ")}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connectSrc.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    `form-action ${formAction.join(" ")}`,
    "frame-ancestors 'none'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
  ];
  if (publicScheme(env) === "https" && deployEnv(env) !== "local") directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

/** Static headers for every response, HTML or not. */
export function baseSecurityHeaders(env: Env = process.env): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy":
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=(), interest-cohort=()",
  };
  if (publicScheme(env) === "https") {
    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains";
  }
  return headers;
}
