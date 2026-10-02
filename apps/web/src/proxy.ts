/**
 * Next.js 16 proxy (formerly middleware): host routing, security headers, noindex and session
 * rotation. The routing decision itself lives in lib/routing/host-routing.ts.
 */
import { NextResponse, type NextRequest } from "next/server";

import { applyWritesToCookieHeader, cookieAttributes, type CookieWrite } from "@/lib/auth/cookies";
import { maintainSession } from "@/lib/auth/proxy-session";
import { resolveRoute, robotsHeader, type RouteDecision } from "@/lib/routing/host-routing";
import { LOCALE_HEADER, NONCE_HEADER, PATHNAME_HEADER, SURFACE_HEADER } from "@/lib/routing/request-headers";
import { baseSecurityHeaders, buildCsp, createNonce } from "@/lib/security/headers";

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
  const decision = resolveRoute({
    host: request.headers.get("host"),
    pathname: request.nextUrl.pathname,
    search: request.nextUrl.search,
  });

  if (decision.type === "asset") return finalize(NextResponse.next(), decision);

  if (decision.type === "redirect") {
    // A relative Location keeps the public scheme and host, whatever terminates TLS upstream.
    return finalize(new NextResponse(null, { status: 307, headers: { Location: decision.location } }), decision);
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

  if (decision.type === "pass") {
    requestHeaders.delete(LOCALE_HEADER);
    return finalize(NextResponse.next({ request: { headers: requestHeaders } }), decision, csp);
  }

  requestHeaders.set(LOCALE_HEADER, decision.locale);
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
