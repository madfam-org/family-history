/** Shared metadata for landing pages: canonical, language alternates and the social image. */
import type { Metadata } from "next";

import { htmlLang, locales, ogLocale, type Locale } from "@/i18n/locales";
import { brandName } from "@/lib/brand";
import { landingOrigin } from "@/lib/env";

export function landingMetadata(input: { locale: Locale; path: string; title: string; description: string }): Metadata {
  const origin = landingOrigin();
  const url = `${origin}/${input.locale}${input.path}`;
  return {
    metadataBase: new URL(origin),
    title: input.title,
    description: input.description,
    alternates: {
      canonical: url,
      languages: Object.fromEntries(locales.map((locale) => [htmlLang[locale], `${origin}/${locale}${input.path}`])),
    },
    openGraph: {
      type: "website",
      url,
      siteName: brandName(input.locale),
      title: input.title,
      description: input.description,
      locale: ogLocale[input.locale],
      images: [{ url: `${origin}/og.png`, width: 1200, height: 630, alt: brandName(input.locale) }],
    },
    twitter: { card: "summary_large_image", title: input.title, description: input.description, images: [`${origin}/og.png`] },
  };
}
