/**
 * Zod schemas for the wave-2 addendum endpoints: kinship (D), compadrazgo (D) and the import and
 * export jobs (E). Shapes the addendum fixes are strict; the job `report`, which it leaves open,
 * is read tolerantly into the parts the UI shows (counts, warnings, extensions).
 */
import { z } from "zod";

/** What `to` is to the person (`KinshipStructure`, from `domain.kinship.Kinship`). */
export const kinshipStructureSchema = z
  .object({
    kind: z.enum(["self", "partner", "blood", "foster", "step", "in_law"]),
    up: z.number().int(),
    down: z.number().int(),
    half: z.boolean().nullable(),
    adoptive: z.boolean(),
    partner_status: z.string().nullable(),
    via: z.string().nullable(),
  })
  .loose();

/** `GET /v1/people/{id}/kinship?to=` (`KinshipOut`). The UI shows only the labels. */
export const kinshipSchema = z.object({
  kinship: kinshipStructureSchema,
  label_es: z.string(),
  label_en: z.string(),
});

export const compadrazgoItemSchema = z.object({
  person_id: z.string(),
  display_name: z.string(),
  relation: z.string(),
  sacrament: z.string().nullable(),
  label_es: z.string(),
  label_en: z.string(),
});

export const compadrazgoSchema = z.object({ items: z.array(compadrazgoItemSchema) });

export const createdAssociationSchema = z.object({ id: z.string() }).loose();

export const EXPORT_FORMATS = ["gedzip", "gedcom7", "gedcom551", "native_json"] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

export const JOB_STATUSES = ["queued", "running", "succeeded", "failed"] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export const jobAcceptedSchema = z.object({ job_id: z.string().min(1) });

const count = z.number().int().nonnegative();
const countMap = z.record(z.string(), count);

/** One diagnostic from the GEDCOM engine (`Diagnostic(severity, code, message, line)`). */
export const diagnosticSchema = z
  .object({
    severity: z.enum(["error", "warning", "info"]).catch("warning"),
    code: z.string(),
    message: z.string().optional(),
    line: z.number().int().nullable().optional(),
  })
  .loose();

/**
 * The import report. The addendum names it but does not fix its shape; this mirrors the GEDCOM
 * engine's `ImportReport` (docs/lanes/gedcom.md) and accepts either `record_counts` or `counts`,
 * either `diagnostics` or `warnings`, and either `extension_tags` or `extensions`.
 */
export const importReportSchema = z
  .object({
    source_version: z.string().nullable().optional(),
    source_product: z.string().nullable().optional(),
    encoding: z.string().nullable().optional(),
    record_counts: countMap.optional(),
    counts: countMap.optional(),
    created_records: countMap.optional(),
    diagnostics: z.array(diagnosticSchema).optional(),
    warnings: z.array(diagnosticSchema).optional(),
    extension_tags: countMap.optional(),
    extensions: countMap.optional(),
  })
  .loose();

export const jobSchema = z.object({
  id: z.string(),
  kind: z.string(),
  status: z.enum(JOB_STATUSES),
  report: z.unknown().optional(),
  error_code: z.string().nullable().optional(),
  created_at: z.string(),
  finished_at: z.string().nullable().optional(),
});

export type Kinship = z.infer<typeof kinshipSchema>;
export type CompadrazgoItem = z.infer<typeof compadrazgoItemSchema>;
export type Compadrazgo = z.infer<typeof compadrazgoSchema>;
export type Diagnostic = z.infer<typeof diagnosticSchema>;
export type Job = z.infer<typeof jobSchema>;

export interface ImportSummary {
  sourceVersion: string | null;
  sourceProduct: string | null;
  counts: Array<[string, number]>;
  created: Array<[string, number]>;
  diagnostics: Diagnostic[];
  extensions: Array<[string, number]>;
}

function entries(map: Record<string, number> | undefined): Array<[string, number]> {
  return Object.entries(map ?? {}).sort(([a], [b]) => a.localeCompare(b));
}

/** Normalises whatever report the API sends; returns null when it is not an import report. */
export function summarizeImportReport(report: unknown): ImportSummary | null {
  const parsed = importReportSchema.safeParse(report);
  if (!parsed.success) return null;
  const data = parsed.data;
  return {
    sourceVersion: data.source_version ?? null,
    sourceProduct: data.source_product ?? null,
    counts: entries(data.record_counts ?? data.counts),
    created: entries(data.created_records),
    diagnostics: data.diagnostics ?? data.warnings ?? [],
    // `_FH_` tags are this platform's own (a re-imported export); only other programs' are listed.
    extensions: entries(data.extension_tags ?? data.extensions).filter(([tag]) => !tag.startsWith("_FH_")),
  };
}

export const JOB_DOWNLOAD_TTL_MS = 24 * 60 * 60 * 1000;

/** When a finished job's download stops working (410 after 24 hours), or null if unknown. */
export function downloadExpiresAt(job: Pick<Job, "status" | "finished_at">): Date | null {
  if (job.status !== "succeeded" || !job.finished_at) return null;
  const finished = Date.parse(job.finished_at);
  return Number.isNaN(finished) ? null : new Date(finished + JOB_DOWNLOAD_TTL_MS);
}

export function isTerminal(status: JobStatus): boolean {
  return status === "succeeded" || status === "failed";
}
