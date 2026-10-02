/**
 * Pure helpers for the relationship, event and godparent editors: which relationship a choice
 * like «Agregar madre» creates, which events take padrinos, and how the editors' fields are read.
 */
import {
  PARTNER_STATUSES,
  PEDIGREES,
  type AssociationRole,
  type PartnerStatus,
  type Pedigree,
  type RelationshipCreateBody,
  type Sex,
} from "@/lib/api/schemas";

export const RELATIVE_KINDS = ["father", "mother", "child", "partner"] as const;
export type RelativeKind = (typeof RELATIVE_KINDS)[number];

export function isRelativeKind(value: unknown): value is RelativeKind {
  return typeof value === "string" && (RELATIVE_KINDS as readonly string[]).includes(value);
}

export function isPedigree(value: unknown): value is Pedigree {
  return typeof value === "string" && (PEDIGREES as readonly string[]).includes(value);
}

export function isPartnerStatus(value: unknown): value is PartnerStatus {
  return typeof value === "string" && (PARTNER_STATUSES as readonly string[]).includes(value);
}

/** The sex a newly created father or mother gets; children and partners are left unknown. */
export function defaultSexFor(kind: RelativeKind): Sex {
  if (kind === "father") return "M";
  if (kind === "mother") return "F";
  return "U";
}

/**
 * The relationship to create between the person on the page and a relative. For
 * `parent_child`, `from_person_id` is the parent (API contract).
 */
export function relationshipFor(
  kind: RelativeKind,
  personId: string,
  relativeId: string,
  qualifier: { pedigree: Pedigree; status: PartnerStatus },
): RelationshipCreateBody {
  switch (kind) {
    case "father":
    case "mother":
      return { type: "parent_child", from_person_id: relativeId, to_person_id: personId, qualifier: qualifier.pedigree };
    case "child":
      return { type: "parent_child", from_person_id: personId, to_person_id: relativeId, qualifier: qualifier.pedigree };
    case "partner":
      return { type: "union", from_person_id: personId, to_person_id: relativeId, qualifier: qualifier.status };
  }
}

/**
 * Events that take padrinos (PRIVACY.md §2: all sacramental, so `religion` by default). The XV
 * años is not a sacrament but has padrinos by custom.
 */
export const GODPARENT_EVENT_TYPES = [
  "baptism",
  "christening",
  "confirmation",
  "first_communion",
  "religious_marriage",
  "quinceanera",
] as const;

export function takesGodparents(eventType: string): boolean {
  return (GODPARENT_EVENT_TYPES as readonly string[]).includes(eventType);
}

/** Event types the editor offers, in the order a family usually records them. */
export const EDITABLE_EVENT_TYPES = [
  "birth",
  "baptism",
  "confirmation",
  "first_communion",
  "quinceanera",
  "civil_marriage",
  "religious_marriage",
  "divorce",
  "residence",
  "occupation",
  "education",
  "emigration",
  "immigration",
  "naturalization",
  "bracero_contract",
  "border_crossing",
  "death",
  "burial",
] as const;
export type EditableEventType = (typeof EDITABLE_EVENT_TYPES)[number];

export function isEditableEventType(value: unknown): value is EditableEventType {
  return typeof value === "string" && (EDITABLE_EVENT_TYPES as readonly string[]).includes(value);
}

/** Marriage events can name the spouse as a second participant. */
export function takesSpouse(eventType: string): boolean {
  return eventType === "civil_marriage" || eventType === "religious_marriage" || eventType === "divorce";
}

export const ASSOCIATION_ROLES: readonly AssociationRole[] = ["godparent", "witness", "officiant", "other"];

export function isAssociationRole(value: unknown): value is AssociationRole {
  return typeof value === "string" && (ASSOCIATION_ROLES as readonly string[]).includes(value);
}

/** `other` needs a phrase (domain: `AssociationRole.OTHER` requires one). */
export function associationNeedsPhrase(role: AssociationRole): boolean {
  return role === "other";
}

export const PHRASE_MAX = 120;
export const DESCRIPTION_MAX = 2000;

/** A UUID-shaped id from a form field, or null. Ids never come from free text. */
export function formId(form: FormData, field: string): string | null {
  const value = String(form.get(field) ?? "").trim();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) ? value.toLowerCase() : null;
}

/** Godparent labels depend on the godparent's sex: padrino, madrina, or both forms. */
export function godparentLabelKey(sex: Sex): "padrino" | "madrina" | "padrinoNeutral" {
  if (sex === "M") return "padrino";
  if (sex === "F") return "madrina";
  return "padrinoNeutral";
}

/**
 * Groups compadrazgo relations for the panel. The addendum leaves `relation`'s vocabulary open,
 * so both Spanish words and English role codes are recognised; anything else is «Otros».
 */
export type CompadrazgoGroup = "godparents" | "godchildren" | "compadres" | "other";

export function compadrazgoGroup(relation: string): CompadrazgoGroup {
  const value = relation.toLowerCase();
  if (/^(padrino|madrina|godparent|godfather|godmother)/.test(value)) return "godparents";
  if (/^(ahijad|godchild|godson|goddaughter)/.test(value)) return "godchildren";
  if (/^(compadre|comadre|co_?parent|coparent)/.test(value)) return "compadres";
  return "other";
}
