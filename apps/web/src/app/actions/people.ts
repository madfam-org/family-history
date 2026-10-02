"use server";

import { redirect } from "next/navigation";

import { isLocale } from "@/i18n/locales";
import { createEvent, createPerson } from "@/lib/api/endpoints";
import { errorMessageKey, isApiError } from "@/lib/api/errors";
import { requireApi } from "@/lib/auth/server";
import { isDateErrorCode } from "@/lib/dates/hints";
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

  // The person exists from here on. The birth date travels as typed (`date_original`, addendum A).
  // If the API refuses it, the editor opens with a hint instead of the date being dropped
  // silently. Only the error kind goes into the URL, never the text.
  let refusal: string | null = null;
  if (parsed.birthDate) {
    try {
      await createEvent(api, spaceId, {
        type: "birth",
        date_original: parsed.birthDate,
        participants: [{ person_id: personId, role: "principal" }],
      });
    } catch (error) {
      if (!isApiError(error)) throw error;
      const code = errorMessageKey(error.code);
      refusal = isDateErrorCode(code) ? code : "other";
    }
  }
  const person = `/${locale}/personas/${encodeURIComponent(personId)}`;
  redirect(refusal ? `${person}/editar?${new URLSearchParams({ fecha: refusal }).toString()}` : person);
}
