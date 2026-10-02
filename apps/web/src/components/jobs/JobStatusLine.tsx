"use client";

import { useTranslations } from "next-intl";

import { errorMessageKey } from "@/lib/api/errors";

import type { JobView } from "./useJob";

/** The job's state, announced politely as it changes; polling failures are shown, not hidden. */
export function JobStatusLine({ view }: { view: JobView }) {
  const t = useTranslations("family.jobs");
  const errors = useTranslations("errors");
  const status = view.job?.status;
  return (
    <div className="flex flex-col gap-2">
      <p role="status" aria-live="polite" className="flex items-center gap-2 font-semibold">
        {status === "queued" || status === "running" || !status ? (
          <span aria-hidden="true" className="inline-block size-3 animate-pulse rounded-full bg-cempasuchil motion-reduce:animate-none" />
        ) : null}
        {status ? t(`status.${status}`) : t("checking")}
      </p>
      {view.error ? (
        <p role="alert" className="font-semibold text-danger">
          {view.stopped ? errors(view.error) : t("pollFailed", { error: errors(view.error) })}
        </p>
      ) : null}
      {status === "failed" ? (
        <p role="alert" className="font-semibold text-danger">
          {errors(errorMessageKey(view.job?.error_code ?? "unknown"))}
        </p>
      ) : null}
    </div>
  );
}
