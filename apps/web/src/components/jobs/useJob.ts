"use client";

import { useEffect, useState } from "react";

import type { ErrorCode } from "@/lib/api/errors";
import { isTerminal, type Job } from "@/lib/api/schemas-family";
import { nextDelay, pollJob, type PollResult } from "@/lib/jobs/polling";

export interface JobView {
  job: Job | null;
  /** The last polling failure; cleared by the next success. */
  error: ErrorCode | null;
  /** True once polling stopped for good on an error that will not fix itself. */
  stopped: boolean;
}

/**
 * Polls a job until it succeeds or fails, backing off gently. Pauses while the tab is hidden
 * (the next poll runs when it becomes visible again).
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
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        document.addEventListener("visibilitychange", tick, { once: true });
        return;
      }
      const result = await poll(jobId as string);
      if (cancelled) return;
      if (result.ok) {
        setView({ job: result.job, error: null, stopped: false });
        if (isTerminal(result.job.status)) return;
      } else {
        setView((current) => ({ ...current, error: result.code, stopped: !result.retry }));
        if (!result.retry) return;
      }
      timer = setTimeout(tick, nextDelay(attempt));
      attempt += 1;
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [jobId, poll]);

  return view;
}
