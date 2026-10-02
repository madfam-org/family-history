import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { ImportPanel } from "@/components/jobs/ImportPanel";
import { isLocale } from "@/i18n/locales";
import { IMPORT_MAX_BYTES, listSpaces } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";

type Params = Promise<{ locale: string; spaceId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "family.import" });
  return { title: t("pageTitle") };
}

/** GEDCOM import, for the space's stewards and editors (the API enforces the same rule). */
export default async function ImportPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, spaceId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const job = (await searchParams).trabajo;
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "family.import" });
  const personCopy = await getTranslations({ locale, namespace: "app.person" });
  const spaceHref = `/${locale}/familias/${encodeURIComponent(spaceId)}`;

  const spaces = await load(() => listSpaces(api));
  if (!spaces.ok) return <ApiErrorNotice locale={locale} code={spaces.code} returnTo={`${spaceHref}/importar`} />;
  const space = spaces.data.find((candidate) => candidate.id === spaceId);
  if (!space) notFound();
  const allowed = space.role === "steward" || space.role === "editor";
  const jobId = typeof job === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(job) ? job : null;

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <a href={spaceHref} className="text-sm">
          ← {personCopy("breadcrumb")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{t("title")}</h1>
        <p className="mt-2 text-muted">{t("lead")}</p>
      </div>
      {allowed ? (
        <ImportPanel spaceId={spaceId} maxBytes={IMPORT_MAX_BYTES} initialJobId={jobId} spaceHref={spaceHref} />
      ) : (
        <p role="alert" className="rounded-xl border-2 border-line-strong p-5">
          {t("notAllowed")}
        </p>
      )}
    </div>
  );
}
