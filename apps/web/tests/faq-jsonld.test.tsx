import { createTranslator } from "next-intl";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { JsonLd } from "@/components/JsonLd";
import { FaqSection } from "@/components/landing/FaqSection";
import { locales, type Locale } from "@/i18n/locales";
import { loadMessages } from "@/i18n/messages";
import { brandName } from "@/lib/brand";
import { buildFaqItems, FAQ_KEYS } from "@/lib/landing/faq";
import { landingJsonLd, serializeJsonLd } from "@/lib/seo/jsonld";

interface Question {
  "@type": string;
  name: string;
  acceptedAnswer: { "@type": string; text: string };
}

function decodeEntities(text: string): string {
  return text
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

async function renderLanding(locale: Locale) {
  const messages = await loadMessages(locale);
  const t = createTranslator({ locale, messages, namespace: "landing.faq.items" });
  const items = buildFaqItems((key, values) => t(key, values), brandName(locale));
  const html = renderToStaticMarkup(
    <>
      <JsonLd data={landingJsonLd(locale, `https://fh.example.test/${locale}`, items)} />
      <FaqSection title="FAQ" items={items} />
    </>,
  );
  return { html, items };
}

describe.each(locales)("FAQ parity (%s)", (locale) => {
  it("has one JSON-LD question per visible question, in the same order and wording", async () => {
    const { html } = await renderLanding(locale);
    const visibleQuestions = [...html.matchAll(/<dt[^>]*data-faq-question[^>]*>([\s\S]*?)<\/dt>/g)].map((match) =>
      decodeEntities(match[1] ?? ""),
    );
    const visibleAnswers = [...html.matchAll(/<dd[^>]*data-faq-answer[^>]*>([\s\S]*?)<\/dd>/g)].map((match) =>
      decodeEntities(match[1] ?? ""),
    );
    const script = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1];
    expect(script).toBeDefined();
    const graph = JSON.parse(script ?? "{}")["@graph"] as Array<{ "@type": string; mainEntity?: Question[] }>;
    const faq = graph.find((node) => node["@type"] === "FAQPage");
    const structured = faq?.mainEntity ?? [];

    expect(visibleQuestions).toHaveLength(FAQ_KEYS.length);
    expect(structured.map((entry) => entry.name)).toEqual(visibleQuestions);
    expect(structured.map((entry) => entry.acceptedAnswer.text)).toEqual(visibleAnswers);
    expect(graph.map((node) => node["@type"])).toEqual(["Organization", "SoftwareApplication", "FAQPage"]);
  });

  it("puts the brand name into the questions through configuration", async () => {
    const { items } = await renderLanding(locale);
    expect(items[0]?.question).toContain(brandName(locale));
  });

  it("declares no price in structured data", async () => {
    const { html } = await renderLanding(locale);
    expect(html).not.toMatch(/"offers"|"price"/);
  });
});

describe("serializeJsonLd", () => {
  it("escapes < so data can never close the script element", () => {
    expect(serializeJsonLd({ text: "</script><script>alert(1)</script>" })).not.toContain("</script>");
  });
});
