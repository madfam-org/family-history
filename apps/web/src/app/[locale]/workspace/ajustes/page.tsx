import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { isLocale } from "@/i18n/locales";
import { requireSession, signInHref } from "@/lib/auth/server";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.settings" });
  return { title: t("title") };
}

/** Ajustes: account details, account switching (ruling R44) and sign-out. */
export default async function SettingsPage({ params }: { params: Params }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const session = await requireSession();
  const t = await getTranslations({ locale, namespace: "app.settings" });
  const home = `/${locale}`;

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <section className="fh-card" aria-labelledby="cuenta">
        <h2 id="cuenta" className="text-xl font-bold">
          {t("accountTitle")}
        </h2>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt className="font-semibold">{t("name")}</dt>
          <dd className="break-words">{session.name ?? t("notProvided")}</dd>
          <dt className="font-semibold">{t("email")}</dt>
          <dd className="break-all">{session.email ?? t("notProvided")}</dd>
        </dl>
      </section>
      <section className="fh-card flex flex-col gap-4" aria-labelledby="cambiar">
        <h2 id="cambiar" className="text-xl font-bold">
          {t("switchTitle")}
        </h2>
        <div>
          <p className="text-muted">{t("switchBody")}</p>
          <a href={signInHref(home, "select_account")} className="fh-button mt-2">
            {t("switchAccount")}
          </a>
        </div>
        <div>
          <p className="text-muted">{t("otherPersonBody")}</p>
          <a href={signInHref(home, "login")} className="fh-button fh-button-secondary mt-2">
            {t("otherPerson")}
          </a>
        </div>
      </section>
      <section className="fh-card" aria-labelledby="salir">
        <h2 id="salir" className="text-xl font-bold">
          {t("signOutTitle")}
        </h2>
        <p className="text-muted">{t("signOutBody")}</p>
        <form method="post" action="/auth/signout" className="mt-2">
          <input type="hidden" name="locale" value={locale} />
          <button type="submit" className="fh-button fh-button-secondary">
            {t("signOut")}
          </button>
        </form>
      </section>
    </div>
  );
}
