/** Per-request facts the proxy forwards: which host surface, the public path and the nonce. */
import "server-only";

import { headers } from "next/headers";

import { locales, type Locale } from "@/i18n/locales";
import { isIndexable } from "@/lib/env";
import type { Surface } from "@/lib/routing/host-routing";
import { NONCE_HEADER, PATHNAME_HEADER, SURFACE_HEADER } from "@/lib/routing/request-headers";

import { switchLocale } from "./switch-locale";

export async function requestSurface(): Promise<Surface> {
  return (await headers()).get(SURFACE_HEADER) === "app" ? "app" : "landing";
}

export async function requestNonce(): Promise<string | undefined> {
  return (await headers()).get(NONCE_HEADER) ?? undefined;
}

/** Whether pages should carry meta robots noindex (always on the app host). */
export async function pageIsNoindex(): Promise<boolean> {
  return !isIndexable() || (await requestSurface()) === "app";
}

/** The same public page in the other language, for the language switch. */
export async function alternateLocaleHref(current: Locale): Promise<{ locale: Locale; href: string }> {
  const other = locales.find((locale) => locale !== current) ?? current;
  return { locale: other, href: switchLocale((await headers()).get(PATHNAME_HEADER) ?? `/${current}`, other) };
}
