import type { Locale } from "@/i18n/locales";

const LOCALE_PREFIX = /^\/(es|en)(?=\/|$)/;

/** The same public path in another language; a locale-prefixed `return_to` follows along. */
export function switchLocale(path: string, target: Locale): string {
  const [pathname = "", query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  const returnTo = params.get("return_to");
  if (returnTo && LOCALE_PREFIX.test(returnTo)) params.set("return_to", returnTo.replace(LOCALE_PREFIX, `/${target}`));
  const search = params.toString();
  return `/${target}${pathname.replace(LOCALE_PREFIX, "")}${search ? `?${search}` : ""}`;
}
