/**
 * Validation for «Agregar persona» with the Mexican name model: nombre(s), apellido paterno,
 * apellido materno, apodo, sexo (M/F/X/U) and the birth date as free text.
 *
 * The person is created first; the birth date travels as a separate birth event with the text
 * exactly as written. Parsing free text into a GEDCOM 7 DateValue is wired server-side later
 * (docs/lanes/web.md, contract requests).
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

export type PersonSubmission =
  | { ok: true; body: PersonCreateBody; birthDate: string | null }
  | { ok: false; error: PersonFormError };

export function toPersonCreateBody(values: PersonFormValues): PersonSubmission {
  if (!values.given && !values.paternal && !values.maternal) return { ok: false, error: "nameRequired" };
  const names = [values.given, values.paternal, values.maternal, values.nickname];
  if (names.some((value) => value.length > PERSON_FIELD_MAX) || values.birthDate.length > BIRTH_DATE_MAX) {
    return { ok: false, error: "tooLong" };
  }
  return {
    ok: true,
    body: {
      sex: values.sex,
      names: [
        {
          ...(values.given ? { given: values.given } : {}),
          ...(values.paternal ? { apellido_paterno: values.paternal } : {}),
          ...(values.maternal ? { apellido_materno: values.maternal } : {}),
          nicknames: values.nickname ? [values.nickname] : [],
        },
      ],
    },
    birthDate: values.birthDate || null,
  };
}
