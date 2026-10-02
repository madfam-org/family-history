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

export const RELATIONSHIP_TYPE_KEYS = ["parent", "child", "union", "spouse", "sibling"] as const;
export type RelationshipTypeKey = (typeof RELATIONSHIP_TYPE_KEYS)[number] | "other";

export function relationshipTypeKey(type: string): RelationshipTypeKey {
  const normalized = type.toLowerCase();
  return (RELATIONSHIP_TYPE_KEYS as readonly string[]).includes(normalized)
    ? (normalized as RelationshipTypeKey)
    : "other";
}

/** «Nombre(s) Paterno Materno», skipping missing parts. */
export function formatName(parts: {
  given?: string | null | undefined;
  surname_paternal?: string | null | undefined;
  surname_maternal?: string | null | undefined;
  display?: string | null | undefined;
}): string {
  const joined = [parts.given, parts.surname_paternal, parts.surname_maternal].filter(Boolean).join(" ");
  return joined || parts.display || "";
}
