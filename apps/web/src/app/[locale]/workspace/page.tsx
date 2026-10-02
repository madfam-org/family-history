import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { CreateSpaceForm } from "@/components/app/CreateSpaceForm";
import { isLocale } from "@/i18n/locales";
import { getMe } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { errorCopy } from "@/lib/i18n/error-copy";

type Params = Promise<{ locale: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.spaces" });
  return { title: t("title") };
}

/** «Mis familias»: the signed-in user's family spaces, and a form to create one. */
export default async function FamiliesPage({ params }: { params: Params }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "app.spaces" });
  const me = await load(() => getMe(api));
  if (!me.ok) return <ApiErrorNotice locale={locale} code={me.code} returnTo={`/${locale}`} />;
  if (!me.data.early_access) return <ApiErrorNotice locale={locale} code="early_access_required" returnTo={`/${locale}`} />;

  const spaces = me.data.spaces;
  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-bold">{t("title")}</h1>
        <p className="mt-2 text-muted">{t("lead")}</p>
      </div>
      {spaces.length === 0 ? (
        <p className="rounded-xl bg-amate p-5 text-bark">{t("empty")}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {spaces.map((space) => (
            <li key={space.id}>
              <a
                href={`/${locale}/familias/${space.id}`}
                className="fh-card block text-fg no-underline hover:border-accent"
              >
                <span className="block font-serif text-xl font-bold text-accent">{space.name}</span>
                <span className="mt-1 block text-sm text-muted">
                  {t(`roles.${space.role}`)} · {t("peopleCount", { count: space.people_count })}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
      <div className="max-w-xl">
        <CreateSpaceForm
          locale={locale}
          copy={{
            title: t("createTitle"),
            nameLabel: t("nameLabel"),
            nameHint: t("nameHint"),
            create: t("create"),
            creating: t("creating"),
            invalid: { nameRequired: t("errors.nameRequired"), nameTooLong: t("errors.nameTooLong") },
            failed: await errorCopy(locale),
          }}
        />
      </div>
    </div>
  );
}
