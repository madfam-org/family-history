"use server";

import { redirect } from "next/navigation";

import { isLocale } from "@/i18n/locales";
import { createPerson } from "@/lib/api/endpoints";
import { errorMessageKey, isApiError } from "@/lib/api/errors";
import { requireApi } from "@/lib/auth/server";
import { readPersonForm, toPersonCreateBody } from "@/lib/forms/person";
import type { PersonFormState } from "@/lib/forms/types";

export async function createPersonAction(_previous: PersonFormState, form: FormData): Promise<PersonFormState> {
  const rawLocale = form.get("locale");
  const locale = isLocale(rawLocale) ? rawLocale : "es";
  const spaceId = String(form.get("spaceId") ?? "");
  const values = readPersonForm(form);
  const echo = { ...values };
  const parsed = toPersonCreateBody(values);
  if (!parsed.ok) return { status: "invalid", error: parsed.error, values: echo };
  if (!spaceId) return { status: "failed", code: "not_found", values: echo };

  const { api } = await requireApi();
  let personId: string;
  try {
    personId = (await createPerson(api, spaceId, parsed.body)).id;
  } catch (error) {
    if (isApiError(error)) return { status: "failed", code: errorMessageKey(error.code), values: echo };
    throw error;
  }
  redirect(`/${locale}/personas/${encodeURIComponent(personId)}`);
}
