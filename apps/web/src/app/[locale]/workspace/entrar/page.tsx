import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { isLocale } from "@/i18n/locales";
import { getSession, signInHref } from "@/lib/auth/server";
import { safeReturnTo } from "@/lib/auth/transaction";

type Params = Promise<{ locale: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

const ERRORS = ["not_configured", "denied", "expired", "invalid", "unavailable"] as const;
type SignInErrorKey = (typeof ERRORS)[number];

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.signIn" });
  return { title: t("title") };
}

/** Sign-in landing for the app host; also where failed sign-ins land with an explanation. */
export default async function SignInPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const query = await searchParams;
  const t = await getTranslations({ locale, namespace: "app.signIn" });
  const rawError = typeof query.error === "string" ? query.error : undefined;
  const error = ERRORS.find((key): key is SignInErrorKey => key === rawError);
  const returnTo = safeReturnTo(typeof query.return_to === "string" ? query.return_to : undefined, locale);
  if (!error && (await getSession())) redirect(returnTo);
  const signedOut = query.signed_out === "1";

  return (
    <section className="mx-auto flex max-w-md flex-col gap-4 py-8" aria-labelledby="entrar-titulo">
      <h1 id="entrar-titulo" className="text-3xl font-bold">
        {t("title")}
      </h1>
      {signedOut && !error ? (
        <p role="status" className="rounded-lg bg-amate p-4 font-semibold text-bark">
          {t("signedOut")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-lg border-2 border-danger p-4 font-semibold text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}
      <p>{t("body")}</p>
      {error === "not_configured" ? null : (
        <p>
          <a href={signInHref(returnTo)} className="fh-button">
            {t("button")}
          </a>
        </p>
      )}
    </section>
  );
}
