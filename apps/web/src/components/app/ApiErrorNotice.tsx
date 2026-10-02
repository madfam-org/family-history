import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import type { ErrorCode } from "@/lib/api/errors";
import { signInHref } from "@/lib/auth/server";

/**
 * Visible rendering of an API failure. `early_access_required` gets its own panel
 * («Tu cuenta aún no tiene acceso anticipado») with a way to switch accounts.
 */
export async function ApiErrorNotice({ locale, code, returnTo }: { locale: Locale; code: ErrorCode; returnTo: string }) {
  const errors = await getTranslations({ locale, namespace: "errors" });
  if (code === "early_access_required") {
    const t = await getTranslations({ locale, namespace: "app.earlyAccess" });
    return (
      <section className="rounded-xl bg-amate p-6 text-bark" aria-labelledby="acceso-anticipado">
        <h1 id="acceso-anticipado" className="text-2xl font-bold">
          {t("title")}
        </h1>
        <p className="mt-2">{t("body")}</p>
        <p className="mt-4">
          <a href={signInHref(returnTo, "select_account")} className="fh-button">
            {t("switchAccount")}
          </a>
        </p>
      </section>
    );
  }
  const signIn = await getTranslations({ locale, namespace: "app.signIn" });
  return (
    <div role="alert" className="rounded-xl border-2 border-danger p-5">
      <p className="font-semibold text-danger">{errors(code)}</p>
      {code === "unauthorized" ? (
        <p className="mt-3">
          <a href={signInHref(returnTo)} className="fh-button">
            {signIn("button")}
          </a>
        </p>
      ) : null}
    </div>
  );
}
