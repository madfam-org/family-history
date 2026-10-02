import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { htmlLang, locales } from "@/i18n/locales";
import { landingOrigin } from "@/lib/env";

const PATHS = ["", "/aviso-de-privacidad"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  await connection();
  const origin = landingOrigin();
  return PATHS.flatMap((path) =>
    locales.map((locale) => ({
      url: `${origin}/${locale}${path}`,
      changeFrequency: "monthly" as const,
      priority: path === "" ? 1 : 0.3,
      alternates: {
        languages: Object.fromEntries(locales.map((other) => [htmlLang[other], `${origin}/${other}${path}`])),
      },
    })),
  );
}
