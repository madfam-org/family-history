"use client";

import { useTranslations } from "next-intl";

import { summarizeImportReport, type ImportSummary } from "@/lib/api/schemas-family";

const KNOWN_RECORDS = ["INDI", "FAM", "SOUR", "REPO", "OBJE", "NOTE", "SNOTE", "SUBM"] as const;
type KnownRecord = (typeof KNOWN_RECORDS)[number];

function CountList({ entries, label }: { entries: ImportSummary["counts"]; label: (tag: string) => string }) {
  return (
    <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-6 gap-y-1">
      {entries.map(([tag, count]) => (
        <div key={tag} className="contents">
          <dt>{label(tag)}</dt>
          <dd className="fh-date text-right">{count}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The import report in Spanish: what the file held, what was added, every warning (grouped by
 * severity, with its line), and the other programs' extension tags that were kept.
 */
export function ImportReport({ report }: { report: unknown }) {
  const t = useTranslations("family.import");
  const summary = summarizeImportReport(report);
  if (!summary) return <p className="text-muted">{t("noReport")}</p>;
  const recordLabel = (tag: string) =>
    (KNOWN_RECORDS as readonly string[]).includes(tag) ? t(`recordTypes.${tag as KnownRecord}`) : t("recordTypes.other", { tag });
  const severities = ["error", "warning", "info"] as const;

  return (
    <section aria-labelledby="reporte" className="flex flex-col gap-5">
      <h2 id="reporte" className="text-2xl font-bold">
        {t("reportTitle")}
      </h2>
      {summary.sourceProduct || summary.sourceVersion ? (
        <p className="text-muted">
          {summary.sourceProduct ? t("source", { product: summary.sourceProduct }) : null}
          {summary.sourceProduct && summary.sourceVersion ? " · " : null}
          {summary.sourceVersion ? t("version", { version: summary.sourceVersion }) : null}
        </p>
      ) : null}
      {summary.created.length > 0 ? (
        <div>
          <h3 className="text-lg font-bold">{t("createdTitle")}</h3>
          <CountList entries={summary.created} label={recordLabel} />
        </div>
      ) : null}
      {summary.counts.length > 0 ? (
        <div>
          <h3 className="text-lg font-bold">{t("countsTitle")}</h3>
          <CountList entries={summary.counts} label={recordLabel} />
        </div>
      ) : null}
      <div>
        <h3 className="text-lg font-bold">{t("diagnosticsTitle", { count: summary.diagnostics.length })}</h3>
        {summary.diagnostics.length > 0 ? (
          <>
            <p className="mt-1 text-sm text-muted">{t("diagnosticsLead")}</p>
            {severities.map((severity) => {
              const items = summary.diagnostics.filter((item) => item.severity === severity);
              if (items.length === 0) return null;
              return (
                <details key={severity} className="mt-2" open={severity === "error" ? true : undefined}>
                  <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold">
                    {t(`severity.${severity}`)} ({items.length})
                  </summary>
                  <ul className="mt-1 flex flex-col gap-1 text-sm">
                    {items.map((item, index) => (
                      <li key={`${item.code}-${item.line ?? "x"}-${index}`}>
                        <span className="fh-date">{item.code}</span>
                        {typeof item.line === "number" ? <span className="text-muted"> · {t("line", { line: item.line })}</span> : null}
                        {item.message ? (
                          <span className="block text-muted" lang="en">
                            {t("technical")}: {item.message}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </details>
              );
            })}
          </>
        ) : null}
      </div>
      {summary.extensions.length > 0 ? (
        <div>
          <h3 className="text-lg font-bold">{t("extensionsTitle")}</h3>
          <p className="mt-1 text-sm text-muted">{t("extensionsLead")}</p>
          <CountList entries={summary.extensions} label={(tag) => tag} />
        </div>
      ) : null}
    </section>
  );
}
