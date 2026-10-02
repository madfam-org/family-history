import type es from "@messages/es.json";
import type familyEs from "@messages/family.es.json";

import type { Locale } from "./locales";

/**
 * Messages are split by area so no file grows past the size limit: `<locale>.json` holds the
 * landing and app shell, `family.<locale>.json` the tree, editors, kinship and import/export.
 * Each file owns distinct top-level keys, so a shallow merge is exact.
 */
export type Messages = typeof es & typeof familyEs;

export async function loadMessages(locale: Locale): Promise<Messages> {
  switch (locale) {
    case "en": {
      const [base, family] = await Promise.all([import("@messages/en.json"), import("@messages/family.en.json")]);
      return { ...base.default, ...family.default };
    }
    case "es": {
      const [base, family] = await Promise.all([import("@messages/es.json"), import("@messages/family.es.json")]);
      return { ...base.default, ...family.default };
    }
  }
}
