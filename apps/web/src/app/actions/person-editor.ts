"use server";

import { refresh } from "next/cache";

import { createEvent, getPerson, patchEvent, patchPerson } from "@/lib/api/endpoints";
import { requireApi } from "@/lib/auth/server";
import { DATE_INPUT_MAX, normalizeDateInput } from "@/lib/dates/hints";
import { DESCRIPTION_MAX, formId, isEditableEventType, takesSpouse } from "@/lib/forms/family";
import { readNameValues, replacePrimaryName, toNameFormBody } from "@/lib/forms/names";
import type { EditorState } from "@/lib/forms/types";

import { failedState, field, savedState } from "./editor-result";

/** «Editar persona» → nombre: replaces the primary name form and the sex. */
export async function updateNamesAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const personId = formId(form, "personId");
  const values = readNameValues(form);
  const echo: Record<string, string> = { ...values };
  if (!personId) return { status: "failed", code: "not_found", values: echo };
  const parsed = toNameFormBody(values);
  if (!parsed.ok) return { status: "invalid", error: parsed.error, values: echo };

  const { api } = await requireApi();
  try {
    const person = await getPerson(api, personId);
    await patchPerson(api, personId, { sex: values.sex, names: replacePrimaryName(person.names, parsed.name) });
  } catch (error) {
    return failedState(error, echo);
  }
  refresh();
  return savedState(previous);
}

/** «Agregar evento»: the date travels as typed (`date_original`); the API parses it. */
export async function addEventAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const personId = formId(form, "personId");
  const spaceId = formId(form, "spaceId");
  const spouseId = formId(form, "spouseId");
  const type = field(form, "type");
  const date = normalizeDateInput(String(form.get("date") ?? ""));
  const description = String(form.get("description") ?? "").trim();
  const values = { type, date, description, spouseId: spouseId ?? "" };
  if (!personId || !spaceId) return { status: "failed", code: "not_found", values };
  if (!isEditableEventType(type)) return { status: "invalid", error: "type", values };
  if (date.length > DATE_INPUT_MAX || description.length > DESCRIPTION_MAX) {
    return { status: "invalid", error: "tooLong", values };
  }

  const participants: Array<{ person_id: string; role: "principal" | "spouse" }> = [
    { person_id: personId, role: "principal" },
  ];
  if (spouseId && spouseId !== personId && takesSpouse(type)) participants.push({ person_id: spouseId, role: "spouse" });

  const { api } = await requireApi();
  try {
    await createEvent(api, spaceId, {
      type,
      ...(date ? { date_original: date } : {}),
      ...(description ? { description } : {}),
      participants,
    });
  } catch (error) {
    return failedState(error, values, { dateText: date });
  }
  refresh();
  return savedState(previous);
}

/** «Corregir fecha» on an existing event. */
export async function correctEventDateAction(previous: EditorState, form: FormData): Promise<EditorState> {
  const eventId = formId(form, "eventId");
  const date = normalizeDateInput(String(form.get("date") ?? ""));
  const values = { date };
  if (!eventId) return { status: "failed", code: "not_found", values };
  if (!date) return { status: "invalid", error: "dateRequired", values };
  if (date.length > DATE_INPUT_MAX) return { status: "invalid", error: "tooLong", values };

  const { api } = await requireApi();
  try {
    await patchEvent(api, eventId, { date_original: date });
  } catch (error) {
    return failedState(error, values, { dateText: date });
  }
  refresh();
  return savedState(previous);
}
