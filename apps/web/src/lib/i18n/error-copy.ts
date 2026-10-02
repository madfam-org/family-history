import "server-only";

import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { KNOWN_ERROR_CODES, type ErrorCode } from "@/lib/api/errors";

/** Every API error code's message, for client forms that render action failures. */
export async function errorCopy(locale: Locale): Promise<Record<ErrorCode, string>> {
  const t = await getTranslations({ locale, namespace: "errors" });
  return Object.fromEntries(KNOWN_ERROR_CODES.map((code) => [code, t(code)])) as Record<ErrorCode, string>;
}
