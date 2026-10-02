import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { isLocale } from "@/i18n/locales";
import { waitlistConfig } from "@/lib/env";
import { landingMetadata } from "@/lib/seo/metadata";
import { loadAviso } from "@/lib/waitlist/aviso";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "meta" });
  return landingMetadata({ locale, path: "/aviso-de-privacidad", title: t("avisoTitle"), description: t("avisoTitle") });
}

/**
 * Renders the counsel-reviewed notice for FH_AVISO_VERSION. With no version, or no published
 * file for it, the page says the notice is under review. No legal text is written in code.
 */
export default async function AvisoPage({ params }: { params: Params }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "aviso" });
  const version = waitlistConfig().avisoVersion;
  const blocks = version ? await loadAviso(version, locale) : null;

  if (!version || !blocks) {
    return (
      <article className="fh-container max-w-3xl py-12">
        <h1 className="text-3xl font-bold">{t("inReviewTitle")}</h1>
        <p className="mt-4 text-lg">{t("inReviewBody")}</p>
      </article>
    );
  }

  return (
    <article className="fh-container max-w-3xl py-12">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p className="fh-date mt-2 text-muted">{t("version", { version })}</p>
      <div className="mt-8 flex flex-col gap-4">
        {blocks.map((block, index) =>
          block.kind === "heading" ? (
            <h2 key={index} className="mt-4 text-2xl font-bold">
              {block.text}
            </h2>
          ) : (
            <p key={index}>{block.text}</p>
          ),
        )}
      </div>
    </article>
  );
}
