import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { brandTagline } from "@/lib/brand";

export async function Hero({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "landing.hero" });
  return (
    <section aria-labelledby="hero-titulo" className="fh-container py-12 md:py-20">
      <p className="inline-flex rounded-full bg-amate px-3 py-1 text-sm font-semibold text-bark">{t("eyebrow")}</p>
      <h1 id="hero-titulo" className="mt-4 max-w-3xl text-4xl font-bold md:text-6xl">
        {t("title")}
      </h1>
      <p className="mt-4 max-w-2xl font-serif text-xl text-accent">{brandTagline(locale)}</p>
      <p className="mt-4 max-w-2xl text-lg">{t("lead")}</p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <a href="#como-funciona" className="fh-button">
          {t("ctaPrimary")}
        </a>
        <a href="#privacidad" className="fh-button fh-button-secondary">
          {t("ctaSecondary")}
        </a>
      </div>
      <p className="mt-6 max-w-2xl text-sm text-muted">{t("status")}</p>
    </section>
  );
}
