import type es from "@messages/es.json";

import type { Locale } from "./locales";

export type Messages = typeof es;

export async function loadMessages(locale: Locale): Promise<Messages> {
  switch (locale) {
    case "en":
      return (await import("@messages/en.json")).default;
    case "es":
      return (await import("@messages/es.json")).default;
  }
}
