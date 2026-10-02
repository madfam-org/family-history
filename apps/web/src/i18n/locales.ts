export const locales = ["es", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "es";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}

/** BCP 47 tags for <html lang> and OpenGraph. Spanish is Mexican Spanish first. */
export const htmlLang: Readonly<Record<Locale, string>> = { es: "es-MX", en: "en" };
export const ogLocale: Readonly<Record<Locale, string>> = { es: "es_MX", en: "en_US" };
