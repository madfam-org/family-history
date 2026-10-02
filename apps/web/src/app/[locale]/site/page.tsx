import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { JsonLd } from "@/components/JsonLd";
import { FaqSection } from "@/components/landing/FaqSection";
import { FeatureSection } from "@/components/landing/FeatureSection";
import { Hero } from "@/components/landing/Hero";
import { WaitlistSection } from "@/components/landing/WaitlistSection";
import { isLocale, type Locale } from "@/i18n/locales";
import { brandName } from "@/lib/brand";
import { landingOrigin } from "@/lib/env";
import { buildFaqItems } from "@/lib/landing/faq";
import { landingJsonLd } from "@/lib/seo/jsonld";
import { landingMetadata } from "@/lib/seo/metadata";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "meta" });
  const brand = brandName(locale);
  return landingMetadata({
    locale,
    path: "",
    title: t("landingTitle", { brand }),
    description: t("landingDescription"),
  });
}

const HOW_KEYS = ["tree", "stories", "privacy", "export"] as const;
const MEXICAN_KEYS = ["surnames", "compadrazgo", "records", "muertos"] as const;
const PROMISE_KEYS = ["living", "dna", "noSale", "export"] as const;

async function sections(locale: Locale) {
  const how = await getTranslations({ locale, namespace: "landing.how" });
  const mexican = await getTranslations({ locale, namespace: "landing.mexican" });
  const promises = await getTranslations({ locale, namespace: "landing.promises" });
  return {
    how: {
      title: how("title"),
      lead: how("lead"),
      features: HOW_KEYS.map((key) => ({ key, title: how(`items.${key}.title`), body: how(`items.${key}.body`) })),
    },
    mexican: {
      title: mexican("title"),
      lead: mexican("lead"),
      features: MEXICAN_KEYS.map((key) => ({
        key,
        title: mexican(`items.${key}.title`),
        body: mexican(`items.${key}.body`),
      })),
    },
    promises: {
      title: promises("title"),
      lead: promises("lead"),
      features: PROMISE_KEYS.map((key) => ({
        key,
        title: promises(`items.${key}.title`),
        body: promises(`items.${key}.body`),
      })),
    },
  };
}

export default async function LandingPage({ params }: { params: Params }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);

  const faqT = await getTranslations({ locale, namespace: "landing.faq" });
  const faqItems = buildFaqItems((key, values) => faqT(`items.${key}`, values), brandName(locale));
  const content = await sections(locale);
  const pageUrl = `${landingOrigin()}/${locale}`;

  return (
    <>
      <JsonLd data={landingJsonLd(locale, pageUrl, faqItems)} />
      <Hero locale={locale} />
      <FeatureSection id="como-funciona" {...content.how} />
      <FeatureSection id="familias-mexicanas" tone="amate" highlightKey="muertos" {...content.mexican} />
      <FeatureSection id="privacidad" {...content.promises} />
      <WaitlistSection locale={locale} />
      <FaqSection title={faqT("title")} items={faqItems} />
    </>
  );
}
