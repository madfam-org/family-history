import { landingOrigin } from "@/lib/env";
import { buildLlmsTxt } from "@/lib/seo/llms";

export const dynamic = "force-dynamic";

export function GET(): Response {
  return new Response(buildLlmsTxt(landingOrigin()), {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=3600" },
  });
}
