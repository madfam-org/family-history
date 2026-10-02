/**
 * robots.txt rules.
 * - Not indexable (FH_INDEXABLE not exactly `true`), or the app host: disallow everything.
 * - Indexable landing host (MADFAM ruling R40): the named AI and search crawlers may read the
 *   landing paths; app and API paths are disallowed for everyone.
 */
import type { MetadataRoute } from "next";

import type { Surface } from "@/lib/routing/host-routing";

export const R40_AGENTS = [
  "ClaudeBot",
  "anthropic-ai",
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "PerplexityBot",
  "Google-Extended",
  "CCBot",
  "Applebot-Extended",
] as const;

export const LANDING_ALLOW = ["/", "/es", "/en", "/llms.txt"];
export const APP_AND_API_DISALLOW = ["/auth/", "/api/"];

export function buildRobots(input: { indexable: boolean; surface: Surface; landingOrigin: string }): MetadataRoute.Robots {
  if (!input.indexable || input.surface === "app") {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }
  return {
    rules: [
      { userAgent: [...R40_AGENTS], allow: LANDING_ALLOW, disallow: APP_AND_API_DISALLOW },
      { userAgent: "*", allow: LANDING_ALLOW, disallow: APP_AND_API_DISALLOW },
    ],
    sitemap: `${input.landingOrigin}/sitemap.xml`,
    host: input.landingOrigin,
  };
}
