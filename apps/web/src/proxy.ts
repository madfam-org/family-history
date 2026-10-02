/**
 * Next.js 16 proxy (formerly middleware): host routing, security headers, noindex and session
 * rotation. The routing decision itself lives in lib/routing/host-routing.ts.
 */
import { randomBytes } from "node:crypto";

import { NextResponse, type NextRequest } from "next/server";

import { applyWritesToCookieHeader, cookieAttributes, type CookieWrite } from "@/lib/auth/cookies";
import { maintainSession } from "@/lib/auth/proxy-session";
import { appOrigin, landingOrigin } from "@/lib/env";
import { resolveRoute, robotsHeader, type RouteDecision } from "@/lib/routing/host-routing";
import { LOCALE_HEADER, NONCE_HEADER, PATHNAME_HEADER, SURFACE_HEADER } from "@/lib/routing/request-headers";
import { baseSecurityHeaders, buildCsp, createNonce } from "@/lib/security/headers";

/**
 * In the standalone server Next.js runs the proxy again on a rewrite's destination. The first
 * pass marks the rewritten request with a per-process secret so the second pass lets it through;
 * a client cannot forge the marker, so internal route trees stay unreachable from outside.
 */
const INTERNAL_HEADER = "x-fh-internal";
const INTERNAL_TOKEN = randomBytes(24).toString("base64url");

function finalize(response: NextResponse, decision: RouteDecision, csp?: string): NextResponse {
  for (const [key, value] of Object.entries(baseSecurityHeaders())) response.headers.set(key, value);
  if (csp) response.headers.set("Content-Security-Policy", csp);
  const robots = robotsHeader(decision.surface);
  if (robots) response.headers.set("X-Robots-Tag", robots);
  return response;
}

function applyCookieWrites(response: NextResponse, writes: readonly CookieWrite[]): void {
  const attributes = cookieAttributes();
  for (const write of writes) {
    response.cookies.set(write.name, write.value, { ...attributes, maxAge: write.maxAge });
  }
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  if (request.headers.get(INTERNAL_HEADER) === INTERNAL_TOKEN) return NextResponse.next();

  const decision = resolveRoute({
    host: request.headers.get("host"),
    pathname: request.nextUrl.pathname,
    search: request.nextUrl.search,
  });

  if (decision.type === "asset") return finalize(NextResponse.next(), decision);

  if (decision.type === "redirect") {
    // Absolute on the public origin, whatever terminates TLS upstream; unknown hosts go to the landing.
    const origin = decision.surface === "app" ? appOrigin() : landingOrigin();
    return finalize(NextResponse.redirect(new URL(decision.location, origin), 307), decision);
  }

  if (decision.type === "not_found") {
    return finalize(
      new NextResponse("Not found", { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } }),
      decision,
    );
  }

  const nonce = createNonce();
  const csp = buildCsp(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(NONCE_HEADER, nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  requestHeaders.set(SURFACE_HEADER, decision.surface);
  requestHeaders.set(PATHNAME_HEADER, `${request.nextUrl.pathname}${request.nextUrl.search}`);
  requestHeaders.delete(INTERNAL_HEADER);

  if (decision.type === "pass") {
    requestHeaders.delete(LOCALE_HEADER);
    return finalize(NextResponse.next({ request: { headers: requestHeaders } }), decision, csp);
  }

  requestHeaders.set(LOCALE_HEADER, decision.locale);
  requestHeaders.set(INTERNAL_HEADER, INTERNAL_TOKEN);
  let writes: CookieWrite[] = [];
  if (decision.surface === "app") {
    const existing = request.cookies.getAll().map(({ name, value }) => ({ name, value }));
    writes = await maintainSession(existing);
    if (writes.length > 0) requestHeaders.set("cookie", applyWritesToCookieHeader(existing, writes));
  }
  const target = new URL(`${decision.pathname}${request.nextUrl.search}`, request.nextUrl);
  const response = NextResponse.rewrite(target, { request: { headers: requestHeaders } });
  applyCookieWrites(response, writes);
  return finalize(response, decision, csp);
}

export const config = {
  matcher: ["/:path*"],
};
