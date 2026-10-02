import type { MetadataRoute } from "next";
import { headers } from "next/headers";

import { isIndexable, landingOrigin } from "@/lib/env";
import { surfaceForHost } from "@/lib/routing/host-routing";
import { buildRobots } from "@/lib/seo/robots";

export default async function robots(): Promise<MetadataRoute.Robots> {
  const host = (await headers()).get("host");
  return buildRobots({ indexable: isIndexable(), surface: surfaceForHost(host), landingOrigin: landingOrigin() });
}
