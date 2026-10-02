"use server";

import { redirect } from "next/navigation";

import { isLocale } from "@/i18n/locales";
import { createSpace } from "@/lib/api/endpoints";
import { errorMessageKey, isApiError } from "@/lib/api/errors";
import { requireApi } from "@/lib/auth/server";
import { parseSpaceForm } from "@/lib/forms/space";
import type { SpaceFormState } from "@/lib/forms/types";

export async function createSpaceAction(_previous: SpaceFormState, form: FormData): Promise<SpaceFormState> {
  const rawLocale = form.get("locale");
  const locale = isLocale(rawLocale) ? rawLocale : "es";
  const values = { name: String(form.get("name") ?? "") };
  const parsed = parseSpaceForm(form);
  if (!parsed.ok) return { status: "invalid", error: parsed.error, values };

  const { api } = await requireApi();
  let spaceId: string;
  try {
    spaceId = (await createSpace(api, parsed.name)).id;
  } catch (error) {
    if (isApiError(error)) return { status: "failed", code: errorMessageKey(error.code), values };
    throw error;
  }
  redirect(`/${locale}/familias/${encodeURIComponent(spaceId)}`);
}
