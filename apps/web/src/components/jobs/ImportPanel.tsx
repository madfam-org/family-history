"use client";

import { useLocale, useTranslations } from "next-intl";
import { useId, useState, type FormEvent } from "react";

import { errorMessageKey, type ErrorCode } from "@/lib/api/errors";
import { errorEnvelopeSchema } from "@/lib/api/schemas";
import { jobAcceptedSchema } from "@/lib/api/schemas-family";
import { checkImportFile, formatBytes, IMPORT_EXTENSIONS, type ImportFileProblem } from "@/lib/jobs/polling";

import { ImportReport } from "./ImportReport";
import { JobStatusLine } from "./JobStatusLine";
import { useJob } from "./useJob";

/**
 * Upload a .ged or .gdz (≤ 25 MiB), then follow the import job and show its report. The job id
 * goes into the URL (`?trabajo=`) so a reload keeps following it.
 */
export function ImportPanel({
  spaceId,
  maxBytes,
  initialJobId,
  spaceHref,
}: {
  spaceId: string;
  maxBytes: number;
  initialJobId: string | null;
  spaceHref: string;
}) {
  const t = useTranslations("family.import");
  const errors = useTranslations("errors");
  const locale = useLocale();
  const inputId = useId();
  const hintId = useId();
  const [jobId, setJobId] = useState<string | null>(initialJobId);
  const [problem, setProblem] = useState<{ kind: ImportFileProblem; size?: number } | null>(null);
  const [failure, setFailure] = useState<ErrorCode | null>(null);
  const [uploading, setUploading] = useState(false);
  const view = useJob(jobId);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    const file = (new FormData(event.currentTarget).get("file") as File | null) ?? null;
    const kind = checkImportFile(file, maxBytes);
    if (kind) {
      setProblem({ kind, size: file?.size ?? 0 });
      return;
    }
    setProblem(null);
    setUploading(true);
    try {
      const body = new FormData();
      body.set("file", file as File);
      const response = await fetch(`/api/app/spaces/${encodeURIComponent(spaceId)}/imports`, {
        method: "POST",
        body,
        credentials: "same-origin",
      });
      const payload: unknown = await response.json().catch(() => null);
      const accepted = jobAcceptedSchema.safeParse(payload);
      if (response.ok && accepted.success) {
        setJobId(accepted.data.job_id);
        const url = new URL(window.location.href);
        url.searchParams.set("trabajo", accepted.data.job_id);
        window.history.replaceState(window.history.state, "", url);
      } else {
        const envelope = errorEnvelopeSchema.safeParse(payload);
        setFailure(envelope.success ? errorMessageKey(envelope.data.error.code) : "unknown");
      }
    } catch {
      setFailure("api_unreachable");
    } finally {
      setUploading(false);
    }
  }

  function startOver() {
    setJobId(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("trabajo");
    window.history.replaceState(window.history.state, "", url);
  }

  if (jobId) {
    const done = view.job?.status === "succeeded" || view.job?.status === "failed" || view.stopped;
    return (
      <div className="flex flex-col gap-4">
        <div className="fh-card flex flex-col gap-2">
          {!done ? <p>{t("started")}</p> : null}
          <JobStatusLine view={view} />
        </div>
        {view.job?.status === "succeeded" ? (
          <div className="fh-card">
            <ImportReport report={view.job.report} />
          </div>
        ) : null}
        {done ? (
          <p className="flex flex-wrap gap-2">
            <a href={spaceHref} className="fh-button">
              {t("openSpace")}
            </a>
            <button type="button" className="fh-button fh-button-secondary" onClick={startOver}>
              {t("another")}
            </button>
          </p>
        ) : null}
      </div>
    );
  }

  const problemText = problem
    ? problem.kind === "tooLarge"
      ? t("tooLarge", { size: formatBytes(problem.size ?? 0, locale) })
      : t(problem.kind)
    : null;
  return (
    <form onSubmit={submit} className="fh-card flex flex-col gap-4" encType="multipart/form-data">
      <div className="flex flex-col gap-1">
        <label htmlFor={inputId} className="font-semibold">
          {t("file")}
        </label>
        <input
          id={inputId}
          name="file"
          type="file"
          accept={IMPORT_EXTENSIONS.join(",")}
          aria-describedby={hintId}
          aria-invalid={problem ? true : undefined}
          className="fh-input"
        />
        <p id={hintId} className="text-sm text-muted">
          {t("fileHint")}
        </p>
      </div>
      {problemText || failure ? (
        <p role="alert" className="font-semibold text-danger">
          {problemText ?? (failure ? errors(failure) : "")}
        </p>
      ) : null}
      <button type="submit" className="fh-button self-start" disabled={uploading}>
        {uploading ? t("uploading") : t("submit")}
      </button>
    </form>
  );
}
