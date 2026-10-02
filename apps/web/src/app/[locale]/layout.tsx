import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { defaultLocale, htmlLang, isLocale, locales } from "@/i18n/locales";
import { brand, brandName } from "@/lib/brand";
import { fontVariables } from "@/lib/fonts";
import { pageIsNoindex } from "@/lib/i18n/request-context";

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const noindex = await pageIsNoindex();
  return {
    robots: noindex ? { index: false, follow: false, nocache: true } : { index: true, follow: true },
    applicationName: brandName(isLocale(locale) ? locale : defaultLocale),
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: brand.colors.paper },
    { media: "(prefers-color-scheme: dark)", color: brand.colors.ink },
  ],
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  return (
    <html lang={htmlLang[locale]} className={fontVariables}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
