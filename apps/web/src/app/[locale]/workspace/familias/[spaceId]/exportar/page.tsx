import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ExportFormats, ExportJob } from "@/components/jobs/ExportPanel";
import { isLocale } from "@/i18n/locales";
import { errorMessageKey } from "@/lib/api/errors";
import { EXPORT_FORMATS, type ExportFormat } from "@/lib/api/schemas-family";
import { requireSession } from "@/lib/auth/server";
import { asId } from "@/lib/forms/family";

type Params = Promise<{ locale: string; spaceId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "family.export" });
  return { title: t("pageTitle") };
}

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * «Llévate todo»: full export in four formats, for every member and every plan (AGENTS.md
 * doctrine 4: the exit is free). Nothing on this page checks a plan or a role.
 */
export default async function ExportPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, spaceId } = await params;
  if (!isLocale(locale) || !asId(spaceId)) notFound();
  setRequestLocale(locale);
  await requireSession();
  const query = await searchParams;
  const t = await getTranslations({ locale, namespace: "family.export" });
  const personCopy = await getTranslations({ locale, namespace: "app.person" });
  const spaceHref = `/${locale}/familias/${encodeURIComponent(spaceId)}`;
  const here = `${spaceHref}/exportar`;

  const rawJob = single(query.trabajo);
  const jobId = rawJob && /^[A-Za-z0-9_-]{1,128}$/.test(rawJob) ? rawJob : null;
  const rawFormat = single(query.formato);
  const format = rawFormat && (EXPORT_FORMATS as readonly string[]).includes(rawFormat) ? (rawFormat as ExportFormat) : null;
  const rawError = single(query.error);
  const returnedError = rawError ? errorMessageKey(rawError) : null;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <a href={spaceHref} className="text-sm">
          ← {personCopy("breadcrumb")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{t("title")}</h1>
        <p className="mt-2 text-lg">{t("lead")}</p>
        <p className="mt-3 inline-flex rounded-full bg-amate px-3 py-1 font-semibold text-bark">{t("free")}</p>
      </div>
      {jobId ? (
        <ExportJob
          jobId={jobId}
          format={format}
          back={here}
          returnedError={returnedError}
          startOverHref={here}
        />
      ) : (
        <ExportFormats locale={locale} spaceId={spaceId} />
      )}
    </div>
  );
}
