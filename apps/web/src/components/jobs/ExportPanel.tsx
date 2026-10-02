"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import { startExportAction } from "@/app/actions/jobs";
import { FormStatus } from "@/components/family/FormStatus";
import type { ErrorCode } from "@/lib/api/errors";
import { downloadExpiresAt, EXPORT_FORMATS, type ExportFormat } from "@/lib/api/schemas-family";
import { idleEditorState, type EditorState } from "@/lib/forms/types";
import { downloadHref } from "@/lib/jobs/polling";

import { JobStatusLine } from "./JobStatusLine";
import { useJob } from "./useJob";

/** One button per format; the server action starts the job and moves to `?trabajo=`. */
export function ExportFormats({ locale, spaceId }: { locale: string; spaceId: string }) {
  const t = useTranslations("family.export");
  const [state, action, pending] = useActionState<EditorState, FormData>(startExportAction, idleEditorState);
  return (
    <section aria-labelledby="formatos" className="flex flex-col gap-4">
      <h2 id="formatos" className="text-2xl font-bold">
        {t("formatsTitle")}
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2">
        {EXPORT_FORMATS.map((format) => (
          <li key={format} className="fh-card flex flex-col gap-3">
            <h3 className="text-lg font-bold">{t(`formats.${format}.name`)}</h3>
            <p className="grow text-muted">{t(`formats.${format}.body`)}</p>
            <form action={action}>
              <input type="hidden" name="locale" value={locale} />
              <input type="hidden" name="spaceId" value={spaceId} />
              <input type="hidden" name="format" value={format} />
              <button type="submit" className="fh-button" disabled={pending} aria-label={`${t("start")}: ${t(`formats.${format}.name`)}`}>
                {pending ? t("starting") : t("start")}
              </button>
            </form>
          </li>
        ))}
      </ul>
      <FormStatus state={state} saved="" />
    </section>
  );
}

/** Follows an export job; when it is ready, the download link and when it stops working. */
export function ExportJob({
  jobId,
  format,
  back,
  returnedError,
  startOverHref,
}: {
  jobId: string;
  format: ExportFormat | null;
  back: string;
  returnedError: ErrorCode | null;
  startOverHref: string;
}) {
  const t = useTranslations("family.export");
  const errors = useTranslations("errors");
  const formatter = useFormatter();
  const view = useJob(returnedError ? null : jobId);
  const expires = view.job ? downloadExpiresAt(view.job) : null;
  const [openedAt] = useState(() => Date.now());
  const expired = returnedError === "download_expired" || (expires !== null && expires.getTime() < openedAt);

  return (
    <div className="fh-card flex flex-col gap-3">
      {format ? <h2 className="text-xl font-bold">{t(`formats.${format}.name`)}</h2> : null}
      {returnedError ? (
        <p role="alert" className="font-semibold text-danger">
          {expired ? t("expired") : errors(returnedError)}
        </p>
      ) : (
        <>
          {view.job?.status !== "succeeded" ? <p>{t("preparing")}</p> : null}
          <JobStatusLine view={view} />
          {view.job?.status === "succeeded" && !expired ? (
            <>
              <p>
                <a href={downloadHref(jobId, back)} className="fh-button" download>
                  {t("download")}
                </a>
              </p>
              {expires ? (
                <p className="text-sm text-muted">
                  {t("expires", { date: formatter.dateTime(expires, { dateStyle: "long", timeStyle: "short" }) })}
                </p>
              ) : null}
            </>
          ) : null}
          {expired ? (
            <p role="alert" className="font-semibold text-danger">
              {t("expired")}
            </p>
          ) : null}
        </>
      )}
      <p>
        <a href={startOverHref}>{t("another")}</a>
      </p>
    </div>
  );
}
