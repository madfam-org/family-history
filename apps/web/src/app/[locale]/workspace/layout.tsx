import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/app/AppHeader";
import { isLocale } from "@/i18n/locales";
import { brandName } from "@/lib/brand";
import { getSession } from "@/lib/auth/server";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "meta" });
  const brand = brandName(locale);
  return { title: { default: `${t("appTitle")} · ${brand}`, template: `%s · ${brand}` } };
}

export default async function WorkspaceLayout({ children, params }: { children: ReactNode; params: Params }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const session = await getSession();
  return (
    <>
      <AppHeader locale={locale} signedIn={session !== null} />
      <main id="contenido" tabIndex={-1} className="fh-container py-8">
        {children}
      </main>
    </>
  );
}
