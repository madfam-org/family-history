/**
 * Host routing for the single web server (docs/ARCHITECTURE.md §Contracts → Hosts).
 *
 * - The landing host serves the public landing under `/es` (default) and `/en`.
 * - The app host serves the signed-in app under `/es` and `/en`, plus `/auth/*`.
 * - Any other host is treated as the landing host.
 *
 * Public paths are rewritten to internal route trees (`/<locale>/site/...` and
 * `/<locale>/workspace/...`); the internal segment names are never reachable from outside.
 * Pure function: no Next.js imports, so it is unit-tested directly.
 */
import { defaultLocale, isLocale, type Locale } from "@/i18n/locales";
import { hostConfig, isIndexable, normalizeHost, type Env } from "@/lib/env";

export type Surface = "landing" | "app";

export const SITE_SEGMENT = "site";
export const WORKSPACE_SEGMENT = "workspace";
const INTERNAL_SEGMENTS = new Set([SITE_SEGMENT, WORKSPACE_SEGMENT]);

/** Served the same way on every host. */
const SHARED_EXACT = new Set([
  "/api/health",
  "/robots.txt",
  "/sitemap.xml",
  "/llms.txt",
  "/og.png",
  "/favicon.ico",
  "/icon.svg",
]);

const AUTH_PATHS = new Set(["/auth/start", "/auth/callback", "/auth/signout"]);

export type RouteDecision =
  | { type: "asset"; surface: Surface }
  | { type: "pass"; surface: Surface }
  | { type: "rewrite"; surface: Surface; locale: Locale; pathname: string }
  | { type: "redirect"; surface: Surface; location: string }
  | { type: "not_found"; surface: Surface };

export function surfaceForHost(host: string | null | undefined, env: Env = process.env): Surface {
  const { appHost } = hostConfig(env);
  return normalizeHost(host) === appHost ? "app" : "landing";
}

export function resolveRoute(
  input: { host: string | null | undefined; pathname: string; search?: string },
  env: Env = process.env,
): RouteDecision {
  const surface = surfaceForHost(input.host, env);
  const { pathname } = input;
  const search = input.search ?? "";

  if (pathname.startsWith("/_next/")) return { type: "asset", surface };
  if (SHARED_EXACT.has(pathname)) return { type: "pass", surface };

  if (AUTH_PATHS.has(pathname)) {
    return surface === "app" ? { type: "pass", surface } : { type: "not_found", surface };
  }

  const segments = pathname.split("/").filter(Boolean);
  const [first, second] = segments;

  if (!isLocale(first)) {
    const rest = pathname === "/" ? "" : pathname;
    return { type: "redirect", surface, location: `/${defaultLocale}${rest}${search}` };
  }
  if (second !== undefined && INTERNAL_SEGMENTS.has(second)) return { type: "not_found", surface };

  const internal = surface === "app" ? WORKSPACE_SEGMENT : SITE_SEGMENT;
  const rest = segments.slice(1).join("/");
  return {
    type: "rewrite",
    surface,
    locale: first,
    pathname: `/${first}/${internal}${rest ? `/${rest}` : ""}`,
  };
}

/**
 * `X-Robots-Tag` for a response. Working hosts (FH_INDEXABLE not exactly `true`) are noindex
 * everywhere; the signed-in app is never indexable.
 */
export function robotsHeader(surface: Surface, env: Env = process.env): string | undefined {
  if (!isIndexable(env) || surface === "app") return "noindex, nofollow";
  return undefined;
}
