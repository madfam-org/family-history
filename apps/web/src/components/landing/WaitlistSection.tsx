import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { loadAviso } from "@/lib/waitlist/aviso";
import { waitlistState } from "@/lib/waitlist/gate";

import { WaitlistForm } from "./WaitlistForm";

/**
 * The form renders only when the gate is open (FH_WAITLIST_ENABLED=true, FH_AVISO_VERSION set
 * and that notice published). Otherwise the honest «Muy pronto» notice shows instead.
 */
export async function WaitlistSection({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "landing.waitlist" });
  const config = waitlistState();
  const open = config.open && (await loadAviso(config.avisoVersion, locale)) !== null;

  return (
    <section id="acceso" aria-labelledby="acceso-titulo" className="fh-container py-12">
      {open ? (
        <div className="max-w-xl">
          <h2 id="acceso-titulo" className="sr-only">
            {t("title")}
          </h2>
          <WaitlistForm
            locale={locale}
            copy={{
              title: t("title"),
              lead: t("lead"),
              emailLabel: t("emailLabel"),
              emailHint: t("emailHint"),
              consentBefore: t("consentBefore"),
              consentLink: t("consentLink"),
              consentAfter: t("consentAfter"),
              submit: t("submit"),
              submitting: t("submitting"),
              successTitle: t("successTitle"),
              successBody: t("successBody"),
              errors: {
                invalidEmail: t("errors.invalidEmail"),
                consentRequired: t("errors.consentRequired"),
                rateLimited: t("errors.rateLimited"),
                unavailable: t("errors.unavailable"),
                closed: t("errors.closed"),
              },
            }}
          />
        </div>
      ) : (
        <div className="rounded-xl bg-amate p-6 text-bark" data-waitlist="soon">
          <h2 id="acceso-titulo" className="text-2xl font-bold">
            {t("soonTitle")}
          </h2>
          <p className="mt-2">{t("soonBody")}</p>
        </div>
      )}
    </section>
  );
}
