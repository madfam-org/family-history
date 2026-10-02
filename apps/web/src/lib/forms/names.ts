/**
 * The Mexican name model for the person editor: nombre(s), apellido paterno and materno with
 * their particles («de», «de la», «del»), apodos, the name in use, and the surname order
 * (paterno first, materno first, or a single surname). Pure.
 *
 * `PATCH /v1/people/{id}` replaces every name form, so the editor changes the primary form and
 * sends the others back unchanged, minus the fields the API only returns (`id`, `position`).
 */
import type { NameForm, NameFormBody, Sex, SurnameOrder } from "@/lib/api/schemas";

export const NAME_PART_MAX = 120;
export const PARTICLE_MAX = 20;
export const NICKNAMES_MAX = 10;
export const SURNAME_ORDERS: readonly SurnameOrder[] = ["paterno_materno", "materno_paterno", "single"];
const SEXES: readonly Sex[] = ["M", "F", "X", "U"];

export type NameFormError = "nameRequired" | "tooLong" | "tooManyNicknames";

export interface NameValues {
  given: string;
  paternal: string;
  maternal: string;
  particlePaternal: string;
  particleMaternal: string;
  nombreUsado: string;
  nicknames: string;
  surnameOrder: SurnameOrder;
  sex: Sex;
}

function text(form: FormData, field: string): string {
  return String(form.get(field) ?? "")
    .trim()
    .replace(/\s+/g, " ");
}

export function readNameValues(form: FormData): NameValues {
  const order = text(form, "surnameOrder");
  const sex = text(form, "sex");
  return {
    given: text(form, "given"),
    paternal: text(form, "paternal"),
    maternal: text(form, "maternal"),
    particlePaternal: text(form, "particlePaternal").toLowerCase(),
    particleMaternal: text(form, "particleMaternal").toLowerCase(),
    nombreUsado: text(form, "nombreUsado"),
    nicknames: text(form, "nicknames"),
    surnameOrder: (SURNAME_ORDERS as readonly string[]).includes(order) ? (order as SurnameOrder) : "paterno_materno",
    sex: (SEXES as readonly string[]).includes(sex) ? (sex as Sex) : "U",
  };
}

/** «Chucho, el Güero» → ["Chucho", "el Güero"]; commas or semicolons separate apodos. */
export function splitNicknames(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[,;]/)
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  ];
}

export type NameSubmission = { ok: true; name: NameFormBody } | { ok: false; error: NameFormError };

export function toNameFormBody(values: NameValues): NameSubmission {
  if (!values.given && !values.paternal && !values.maternal && !values.nombreUsado) {
    return { ok: false, error: "nameRequired" };
  }
  const nicknames = splitNicknames(values.nicknames);
  if (nicknames.length > NICKNAMES_MAX) return { ok: false, error: "tooManyNicknames" };
  const parts = [values.given, values.paternal, values.maternal, values.nombreUsado, ...nicknames];
  const particles = [values.particlePaternal, values.particleMaternal];
  if (parts.some((part) => part.length > NAME_PART_MAX) || particles.some((part) => part.length > PARTICLE_MAX)) {
    return { ok: false, error: "tooLong" };
  }
  const particleBody = {
    ...(values.particlePaternal && values.paternal ? { paterno: values.particlePaternal } : {}),
    ...(values.particleMaternal && values.maternal ? { materno: values.particleMaternal } : {}),
  };
  return {
    ok: true,
    name: {
      ...(values.given ? { given: values.given } : {}),
      ...(values.paternal ? { apellido_paterno: values.paternal } : {}),
      ...(values.maternal ? { apellido_materno: values.maternal } : {}),
      ...(Object.keys(particleBody).length > 0 ? { particles: particleBody } : {}),
      ...(values.nombreUsado ? { nombre_usado: values.nombreUsado } : {}),
      nicknames,
      surname_order: values.surnameOrder,
      is_primary: true,
    },
  };
}

/** The form the editor edits: the primary one, else the first. */
export function primaryName(names: readonly NameForm[]): NameForm | undefined {
  return names.find((name) => name.is_primary) ?? names[0];
}

/** Turns a returned name form back into a request body (drops server-only fields). */
export function nameFormToBody(name: NameForm): NameFormBody {
  const particles = {
    ...(name.particles.paterno ? { paterno: name.particles.paterno } : {}),
    ...(name.particles.materno ? { materno: name.particles.materno } : {}),
  };
  const order = (SURNAME_ORDERS as readonly string[]).includes(name.surname_order ?? "")
    ? (name.surname_order as SurnameOrder)
    : undefined;
  return {
    ...(name.given ? { given: name.given } : {}),
    ...(name.apellido_paterno ? { apellido_paterno: name.apellido_paterno } : {}),
    ...(name.apellido_materno ? { apellido_materno: name.apellido_materno } : {}),
    ...(Object.keys(particles).length > 0 ? { particles } : {}),
    ...(name.nombre_usado ? { nombre_usado: name.nombre_usado } : {}),
    nicknames: name.nicknames,
    ...(order ? { surname_order: order } : {}),
    ...(name.name_type ? { name_type: name.name_type } : {}),
    is_primary: false,
  };
}

/** Every name form for the PATCH: the edited primary first, then the others unchanged. */
export function replacePrimaryName(names: readonly NameForm[], edited: NameFormBody): NameFormBody[] {
  const current = primaryName(names);
  return [edited, ...names.filter((name) => name !== current).map(nameFormToBody)];
}

/** Values to prefill the editor with. */
export function nameValuesFrom(name: NameForm | undefined, sex: Sex): NameValues {
  return {
    given: name?.given ?? name?.nombre_de_pila ?? "",
    paternal: name?.apellido_paterno ?? "",
    maternal: name?.apellido_materno ?? "",
    particlePaternal: name?.particles.paterno ?? "",
    particleMaternal: name?.particles.materno ?? "",
    nombreUsado: name?.nombre_usado ?? "",
    nicknames: (name?.nicknames ?? []).join(", "),
    surnameOrder: (SURNAME_ORDERS as readonly string[]).includes(name?.surname_order ?? "")
      ? (name?.surname_order as SurnameOrder)
      : "paterno_materno",
    sex,
  };
}

/**
 * A preview of the full name in the chosen order, for the editor only (the API's
 * `display_name` is the source of truth once saved).
 */
export function previewName(values: NameValues): string {
  const paterno = [values.particlePaternal, values.paternal].filter(Boolean).join(" ");
  const materno = [values.particleMaternal, values.maternal].filter(Boolean).join(" ");
  const surnames =
    values.surnameOrder === "materno_paterno"
      ? [materno, paterno]
      : values.surnameOrder === "single"
        ? [paterno || materno]
        : [paterno, materno];
  return [values.given, ...surnames].filter(Boolean).join(" ");
}
