/**
 * Client-side polling of an import or export job through /api/app/jobs/<id>. Pure helpers plus
 * one fetch function, so the schedule and the error handling are unit-tested.
 */
import { errorMessageKey, type ErrorCode } from "@/lib/api/errors";
import { errorEnvelopeSchema } from "@/lib/api/schemas";
import { jobSchema, type Job } from "@/lib/api/schemas-family";

export const FIRST_DELAY_MS = 1_000;
export const MAX_DELAY_MS = 10_000;

/** 1 s, 1.5 s, 2.25 s… capped at 10 s: quick for small files, gentle for long imports. */
export function nextDelay(attempt: number): number {
  return Math.min(MAX_DELAY_MS, Math.round(FIRST_DELAY_MS * 1.5 ** Math.max(0, attempt)));
}

export type PollResult = { ok: true; job: Job } | { ok: false; code: ErrorCode; retry: boolean };

/** Failures that will not fix themselves by asking again. */
const FINAL: ReadonlySet<ErrorCode> = new Set(["unauthorized", "forbidden", "not_found", "early_access_required"]);

export async function pollJob(jobId: string, fetchImpl: typeof fetch = fetch): Promise<PollResult> {
  let response: Response;
  try {
    response = await fetchImpl(`/api/app/jobs/${encodeURIComponent(jobId)}`, {
      headers: { accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    return { ok: false, code: "api_unreachable", retry: true };
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = errorEnvelopeSchema.safeParse(payload);
    const code = envelope.success ? errorMessageKey(envelope.data.error.code) : "unknown";
    return { ok: false, code, retry: !FINAL.has(code) };
  }
  const parsed = jobSchema.safeParse(payload);
  return parsed.success ? { ok: true, job: parsed.data } : { ok: false, code: "invalid_response", retry: true };
}

/** The download link for a finished job, returning to `back` (an app path) on failure. */
export function downloadHref(jobId: string, back: string): string {
  return `/api/app/jobs/${encodeURIComponent(jobId)}/download?${new URLSearchParams({ volver: back }).toString()}`;
}

/** GEDCOM 7 or 5.5.1, GEDZIP, or a native «Llévate todo» copy (`family-history-tree/v1`). */
export const IMPORT_EXTENSIONS = [".ged", ".gdz", ".json"] as const;

export type ImportFileProblem = "noFile" | "wrongType" | "tooLarge";

/** Checks a chosen file before uploading; the API enforces the same rules. */
export function checkImportFile(file: { name: string; size: number } | null | undefined, maxBytes: number): ImportFileProblem | null {
  if (!file || file.size === 0) return "noFile";
  const name = file.name.toLowerCase();
  if (!IMPORT_EXTENSIONS.some((extension) => name.endsWith(extension))) return "wrongType";
  if (file.size > maxBytes) return "tooLarge";
  return null;
}

/** «24.3 MiB», «512 KiB»: sizes as the limit is written. */
export function formatBytes(bytes: number, locale: string): string {
  const format = (value: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value);
  if (bytes >= 1024 * 1024) return `${format(bytes / (1024 * 1024))} MiB`;
  if (bytes >= 1024) return `${format(bytes / 1024)} KiB`;
  return `${format(bytes)} B`;
}
