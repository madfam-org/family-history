"use server";

import { redirect } from "next/navigation";

import { isLocale } from "@/i18n/locales";
import { startExport } from "@/lib/api/endpoints";
import { EXPORT_FORMATS, type ExportFormat } from "@/lib/api/schemas-family";
import { requireApi } from "@/lib/auth/server";
import { formId } from "@/lib/forms/family";
import type { EditorState } from "@/lib/forms/types";

import { failedState } from "./editor-result";

/**
 * «Llévate todo»: starts an export job and moves to the page that follows it. Exports are free
 * for everyone, so nothing here checks a plan.
 */
export async function startExportAction(_previous: EditorState, form: FormData): Promise<EditorState> {
  const rawLocale = form.get("locale");
  const locale = isLocale(rawLocale) ? rawLocale : "es";
  const spaceId = formId(form, "spaceId");
  const format = String(form.get("format") ?? "");
  const values = { format };
  if (!spaceId) return { status: "failed", code: "not_found", values };
  if (!(EXPORT_FORMATS as readonly string[]).includes(format)) return { status: "invalid", error: "format", values };

  const { api } = await requireApi();
  let jobId: string;
  try {
    jobId = (await startExport(api, spaceId, format as ExportFormat)).job_id;
  } catch (error) {
    return failedState(error, values);
  }
  const params = new URLSearchParams({ trabajo: jobId, formato: format });
  redirect(`/${locale}/familias/${encodeURIComponent(spaceId)}/exportar?${params.toString()}`);
}
