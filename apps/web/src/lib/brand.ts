/**
 * Brand as configuration (ADR 0001).
 *
 * `family-history` is the permanent internal identity. Everything a family sees as the brand
 * (display name, tagline, endorsement line, palette and type tokens) comes from this one file.
 * Rebranding is a change here plus the message files, never a rename elsewhere. No other module
 * may hard-code the display name.
 */
import type { Locale } from "@/i18n/locales";

type Localized = Readonly<Record<Locale, string>>;

export const brand = {
  /** Interim functional name while the public brand is pending. */
  displayName: {
    es: "Historia Familiar",
    en: "Family History",
  } satisfies Localized,
  tagline: {
    es: "La memoria de tu familia, en tu idioma y bajo tu control.",
    en: "Your family's memory, in your language and under your control.",
  } satisfies Localized,
  endorsement: {
    es: "Hecho por Innovaciones MADFAM S.A.S. de C.V., Cuernavaca, Morelos.",
    en: "Made by Innovaciones MADFAM S.A.S. de C.V., Cuernavaca, Morelos.",
  } satisfies Localized,
  organization: {
    legalName: "Innovaciones MADFAM S.A.S. de C.V.",
    url: "https://madfam.io",
    locality: "Cuernavaca",
    region: "Morelos",
    country: "MX",
  },
  sourceCodeUrl: "https://github.com/madfam-org/family-history",
  license: "AGPL-3.0-only",
  /**
   * Colour tokens. Contrast (WCAG 2.x):
   * - white on grana #9A1F40: 7.9:1; grana on paper: 7.6:1
   * - ink #0A0E27 on dark-grana #F07A98: 7.2:1
   * - bark #6E5236 on amate #EEE3D3: 5.7:1
   * Cempasúchil is a seasonal fill only and is never used for text.
   */
  colors: {
    grana: "#9A1F40",
    granaDark: "#F07A98",
    ink: "#0A0E27",
    paper: "#FAFAFA",
    amate: "#EEE3D3",
    bark: "#6E5236",
    cempasuchil: "#E8890C",
  },
} as const;

export function brandName(locale: Locale): string {
  return brand.displayName[locale];
}

export function brandTagline(locale: Locale): string {
  return brand.tagline[locale];
}

export function brandEndorsement(locale: Locale): string {
  return brand.endorsement[locale];
}
