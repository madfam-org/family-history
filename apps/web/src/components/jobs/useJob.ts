"use client";

import { useEffect, useState } from "react";

import type { ErrorCode } from "@/lib/api/errors";
import { isTerminal, type Job } from "@/lib/api/schemas-family";
import { MAX_DELAY_MS, nextDelay, pollJob, type PollResult } from "@/lib/jobs/polling";

export interface JobView {
  job: Job | null;
  /** The last polling failure; cleared by the next success. */
  error: ErrorCode | null;
  /** True once polling stopped for good on an error that will not fix itself. */
  stopped: boolean;
}

/**
 * Polls a job until it succeeds or fails, backing off gently. While the page is hidden it keeps
 * polling at the slowest pace instead of stopping, so a phone that reports «hidden» (another
 * app in front, some in-app browsers) still shows the result when the family comes back.
 */
export function useJob(jobId: string | null, poll: (id: string) => Promise<PollResult> = pollJob): JobView {
  const [view, setView] = useState<JobView>({ job: null, error: null, stopped: false });

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    async function tick() {
      if (cancelled) return;
      const result = await poll(jobId as string);
      if (cancelled) return;
      if (result.ok) {
        setView({ job: result.job, error: null, stopped: false });
        if (isTerminal(result.job.status)) return;
      } else {
        setView((current) => ({ ...current, error: result.code, stopped: !result.retry }));
        if (!result.retry) return;
      }
      const hidden = typeof document !== "undefined" && document.visibilityState === "hidden";
      timer = setTimeout(tick, hidden ? MAX_DELAY_MS : nextDelay(attempt));
      attempt += 1;
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, poll]);

  return view;
}
