/** Validation for «Crear un espacio familiar». */
export const SPACE_NAME_MAX = 120;

export type SpaceFormError = "nameRequired" | "nameTooLong";

export function parseSpaceForm(form: FormData): { ok: true; name: string } | { ok: false; error: SpaceFormError } {
  const name = String(form.get("name") ?? "").trim().replace(/\s+/g, " ");
  if (!name) return { ok: false, error: "nameRequired" };
  if (name.length > SPACE_NAME_MAX) return { ok: false, error: "nameTooLong" };
  return { ok: true, name };
}
