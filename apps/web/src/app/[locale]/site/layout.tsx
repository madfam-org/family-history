import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { Analytics } from "@/components/site/Analytics";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { isLocale } from "@/i18n/locales";

export default async function SiteLayout({
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
    <>
      <SiteHeader locale={locale} />
      <main id="contenido" tabIndex={-1}>
        {children}
      </main>
      <SiteFooter locale={locale} />
      <Analytics />
    </>
  );
}
