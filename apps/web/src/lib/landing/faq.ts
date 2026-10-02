/**
 * The landing FAQ. The visible FAQ and the FAQPage JSON-LD are both built from this one list,
 * so they match one to one (tested in tests/faq-jsonld.test.tsx).
 */
export const FAQ_KEYS = [
  "whatIs",
  "access",
  "living",
  "dna",
  "data",
  "export",
  "language",
  "openSource",
  "maker",
] as const;

export type FaqKey = (typeof FAQ_KEYS)[number];

export interface FaqItem {
  key: FaqKey;
  question: string;
  answer: string;
}

export type FaqTranslator = (key: `${FaqKey}.question` | `${FaqKey}.answer`, values: { brand: string }) => string;

export function buildFaqItems(t: FaqTranslator, brand: string): FaqItem[] {
  return FAQ_KEYS.map((key) => ({
    key,
    question: t(`${key}.question`, { brand }),
    answer: t(`${key}.answer`, { brand }),
  }));
}
