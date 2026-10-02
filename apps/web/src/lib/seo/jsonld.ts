/** Structured data for the landing: Organization, SoftwareApplication and FAQPage. No price. */
import { htmlLang, type Locale } from "@/i18n/locales";
import { brand, brandName, brandTagline } from "@/lib/brand";
import type { FaqItem } from "@/lib/landing/faq";

const ORGANIZATION_ID = `${brand.organization.url}/#organization`;

export function organizationJsonLd() {
  return {
    "@type": "Organization",
    "@id": ORGANIZATION_ID,
    name: brand.organization.legalName,
    url: brand.organization.url,
    address: {
      "@type": "PostalAddress",
      addressLocality: brand.organization.locality,
      addressRegion: brand.organization.region,
      addressCountry: brand.organization.country,
    },
  };
}

export function softwareApplicationJsonLd(locale: Locale, pageUrl: string) {
  return {
    "@type": "SoftwareApplication",
    "@id": `${pageUrl}#app`,
    name: brandName(locale),
    description: brandTagline(locale),
    url: pageUrl,
    applicationCategory: "LifestyleApplication",
    operatingSystem: "Web",
    inLanguage: [htmlLang.es, htmlLang.en],
    license: "https://www.gnu.org/licenses/agpl-3.0.html",
    isBasedOn: brand.sourceCodeUrl,
    publisher: { "@id": ORGANIZATION_ID },
  };
}

export function faqPageJsonLd(locale: Locale, pageUrl: string, items: readonly FaqItem[]) {
  return {
    "@type": "FAQPage",
    "@id": `${pageUrl}#faq`,
    inLanguage: htmlLang[locale],
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}

export function landingJsonLd(locale: Locale, pageUrl: string, faq: readonly FaqItem[]) {
  return {
    "@context": "https://schema.org",
    "@graph": [organizationJsonLd(), softwareApplicationJsonLd(locale, pageUrl), faqPageJsonLd(locale, pageUrl, faq)],
  };
}

/** Serialises JSON-LD for an inline <script>, escaping `<` so content can never close the tag. */
export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
