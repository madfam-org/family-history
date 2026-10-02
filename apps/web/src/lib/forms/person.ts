/**
 * Validation for «Agregar persona» with the Mexican name model: nombre(s), apellido paterno,
 * apellido materno, apodo, sexo (M/F/X/U) and the birth date as free text. The API stores the
 * date string as written; parsing to a GEDCOM 7 DateValue happens server-side later.
 */
import type { PersonCreateBody, Sex } from "@/lib/api/schemas";

export const PERSON_FIELD_MAX = 120;
export const BIRTH_DATE_MAX = 80;

export type PersonFormError = "nameRequired" | "tooLong";

export interface PersonFormValues {
  given: string;
  paternal: string;
  maternal: string;
  nickname: string;
  sex: Sex;
  birthDate: string;
}

const SEXES: readonly Sex[] = ["M", "F", "X", "U"];

function text(form: FormData, field: string): string {
  return String(form.get(field) ?? "").trim().replace(/\s+/g, " ");
}

export function readPersonForm(form: FormData): PersonFormValues {
  const rawSex = String(form.get("sex") ?? "U");
  return {
    given: text(form, "given"),
    paternal: text(form, "paternal"),
    maternal: text(form, "maternal"),
    nickname: text(form, "nickname"),
    sex: (SEXES as readonly string[]).includes(rawSex) ? (rawSex as Sex) : "U",
    birthDate: text(form, "birthDate"),
  };
}

export function toPersonCreateBody(
  values: PersonFormValues,
): { ok: true; body: PersonCreateBody } | { ok: false; error: PersonFormError } {
  if (!values.given && !values.paternal && !values.maternal) return { ok: false, error: "nameRequired" };
  const names = [values.given, values.paternal, values.maternal, values.nickname];
  if (names.some((value) => value.length > PERSON_FIELD_MAX) || values.birthDate.length > BIRTH_DATE_MAX) {
    return { ok: false, error: "tooLong" };
  }
  return {
    ok: true,
    body: {
      names: [
        {
          given: values.given || null,
          surname_paternal: values.paternal || null,
          surname_maternal: values.maternal || null,
          nicknames: values.nickname ? [values.nickname] : [],
        },
      ],
      sex: values.sex,
      birth: values.birthDate ? { date_original: values.birthDate } : null,
    },
  };
}
