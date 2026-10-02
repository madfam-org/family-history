/** Normalises API event and relationship types (snake_case or GEDCOM tags) to message keys. */
export const EVENT_TYPE_KEYS = [
  "birth",
  "baptism",
  "confirmation",
  "first_communion",
  "marriage",
  "civil_marriage",
  "religious_marriage",
  "death",
  "burial",
  "residence",
] as const;
export type EventTypeKey = (typeof EVENT_TYPE_KEYS)[number] | "other";

const EVENT_ALIASES: Readonly<Record<string, EventTypeKey>> = {
  BIRT: "birth",
  BAPM: "baptism",
  CHR: "baptism",
  CONF: "confirmation",
  FCOM: "first_communion",
  MARR: "marriage",
  DEAT: "death",
  BURI: "burial",
  RESI: "residence",
};

export function eventTypeKey(type: string): EventTypeKey {
  const alias = EVENT_ALIASES[type.toUpperCase()];
  if (alias) return alias;
  const normalized = type.toLowerCase();
  return (EVENT_TYPE_KEYS as readonly string[]).includes(normalized) ? (normalized as EventTypeKey) : "other";
}

export type RelationshipLabelKey = "parentOf" | "childOf" | "union" | "other";

/**
 * How a relationship reads from the point of view of `personId`. For `parent_child`,
 * `from_person_id` is the parent (API contract), so the other person is the parent when this
 * person is the child.
 */
export function relationshipLabelKey(
  relationship: { type: string; from_person_id: string; to_person_id: string },
  personId: string,
): RelationshipLabelKey {
  if (relationship.type === "parent_child") {
    return relationship.to_person_id === personId ? "parentOf" : "childOf";
  }
  if (relationship.type === "union") return "union";
  return "other";
}

/** «Nombre(s) Paterno Materno», skipping missing parts; falls back to the name in use. */
export function formatName(parts: {
  given?: string | null | undefined;
  apellido_paterno?: string | null | undefined;
  apellido_materno?: string | null | undefined;
  nombre_usado?: string | null | undefined;
  nombre_de_pila?: string | null | undefined;
}): string {
  const given = parts.given || parts.nombre_de_pila;
  const joined = [given, parts.apellido_paterno, parts.apellido_materno].filter(Boolean).join(" ");
  return joined || parts.nombre_usado || "";
}
