/**
 * Zod schemas for the v1 API contract (docs/ARCHITECTURE.md §"v1 API used by the web app") and
 * the wave-2 addendum (free-text dates, people fields, associations). Fixed shapes are strict
 * about the fields the UI relies on. Addendum fields are accepted when present and default when
 * absent, so the web keeps working against an API that has not shipped them yet; nothing about
 * privacy defaults to "public" (see `isPrivatePerson`).
 */
import { z } from "zod";

export const roleSchema = z.enum(["steward", "editor", "contributor", "viewer"]);
export const sexSchema = z.enum(["M", "F", "X", "U"]);
export const livingStatusSchema = z.enum(["living", "deceased", "presumed_deceased", "unknown"]);
export const visibilitySchema = z.enum(["space", "private", "public_memorial"]);

export const spaceSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  role: roleSchema,
  people_count: z.number().int().nonnegative(),
});

export const spaceSchema = z
  .object({
    id: z.string().uuid(),
    name: z.string(),
    role: roleSchema.optional(),
    people_count: z.number().int().nonnegative().optional(),
  })
  .loose();

/** Addendum A: a humanized date in both languages, or null when there is no date. */
export const dateDisplaySchema = z.object({ es: z.string(), en: z.string() }).nullable();

export const eventBriefSchema = z.object({
  date_value: z.string().nullable(),
  date_display: dateDisplaySchema.default(null),
  place: z.string().nullable(),
});

export const personSummarySchema = z.object({
  id: z.string(),
  display_name: z.string(),
  sort_name: z.string().nullable().optional(),
  sex: sexSchema,
  living_status: livingStatusSchema,
  is_private: z.boolean().optional(),
  birth: eventBriefSchema.nullable(),
  death: eventBriefSchema.nullable(),
  visibility: visibilitySchema,
});

export const peoplePageSchema = z.object({
  items: z.array(personSummarySchema),
  next_cursor: z.string().nullable(),
});

export const meSchema = z.object({
  sub: z.string(),
  email: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  early_access: z.boolean(),
  spaces: z.array(spaceSummarySchema),
});

const optionalText = z.string().nullable().optional();

export const surnameOrderSchema = z.enum(["paterno_materno", "materno_paterno", "single"]);

export const nameFormSchema = z
  .object({
    id: z.string().optional(),
    given: optionalText,
    apellido_paterno: optionalText,
    apellido_materno: optionalText,
    extra_surnames: z.array(z.string()).default([]),
    particles: z.record(z.string(), z.string()).default({}),
    nombre_de_pila: optionalText,
    nombre_usado: optionalText,
    nicknames: z.array(z.string()).default([]),
    name_type: optionalText,
    lang: optionalText,
    surname_order: optionalText,
    is_primary: z.boolean().optional(),
  })
  .loose();

export const associationRoleSchema = z.enum(["godparent", "witness", "officiant", "other"]);

/** An association on an event (addendum D). Where the API returns them is not fixed yet. */
export const associationSchema = z
  .object({
    id: z.string(),
    event_id: z.string().optional(),
    person_id: z.string(),
    display_name: optionalText,
    role: z.string(),
    phrase: optionalText,
  })
  .loose();

export const participantSchema = z.object({ person_id: z.string(), role: z.string() }).loose();

export const personEventSchema = z
  .object({
    id: z.string().optional(),
    type: z.string(),
    date_value: optionalText,
    date_original: optionalText,
    date_display: dateDisplaySchema.optional(),
    date_earliest: optionalText,
    date_latest: optionalText,
    place: optionalText,
    description: optionalText,
    sensitivity: optionalText,
    participants: z.array(participantSchema).default([]),
    associations: z.array(associationSchema).default([]),
  })
  .loose();

export const relationshipSchema = z
  .object({
    id: z.string(),
    type: z.string(),
    from_person_id: z.string(),
    to_person_id: z.string(),
    qualifier: optionalText,
    status: optionalText,
  })
  .loose();

export const citationSchema = z
  .object({
    id: z.string(),
    page: optionalText,
    foja: optionalText,
    partida: optionalText,
  })
  .loose();

/**
 * The full person. The API's `Person` carries events instead of the summary's `birth` and
 * `death` briefs, so those two are optional here (wave-1 web required them; see
 * docs/lanes/integration-web.md).
 */
export const personSchema = personSummarySchema
  .extend({
    birth: eventBriefSchema.nullable().optional(),
    death: eventBriefSchema.nullable().optional(),
    space_id: z.string().optional(),
    names: z.array(nameFormSchema).default([]),
    events: z.array(personEventSchema).default([]),
    relationships: z.array(relationshipSchema).default([]),
    citations: z.array(citationSchema).default([]),
  })
  .loose();

export const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string().regex(/^[a-z][a-z0-9_]*$/),
    message: z.string(),
  }),
});

export type Role = z.infer<typeof roleSchema>;
export type LivingStatus = z.infer<typeof livingStatusSchema>;
export type DateDisplay = z.infer<typeof dateDisplaySchema>;
export type SurnameOrder = z.infer<typeof surnameOrderSchema>;
export type Association = z.infer<typeof associationSchema>;
export type AssociationRole = z.infer<typeof associationRoleSchema>;
export type Sex = z.infer<typeof sexSchema>;
export type SpaceSummary = z.infer<typeof spaceSummarySchema>;
export type Space = z.infer<typeof spaceSchema>;
export type EventBrief = z.infer<typeof eventBriefSchema>;
export type PersonSummary = z.infer<typeof personSummarySchema>;
export type PeoplePage = z.infer<typeof peoplePageSchema>;
export type Me = z.infer<typeof meSchema>;
export type NameForm = z.infer<typeof nameFormSchema>;
export type PersonEvent = z.infer<typeof personEventSchema>;
export type Relationship = z.infer<typeof relationshipSchema>;
export type Citation = z.infer<typeof citationSchema>;
export type Person = z.infer<typeof personSchema>;

/**
 * Whether a person is private to the family space. The addendum's `is_private` wins; without it
 * the web errs toward privacy (docs/PRIVACY.md §1): living and unknown people are private.
 */
export function isPrivatePerson(person: { is_private?: boolean | undefined; living_status: LivingStatus }): boolean {
  if (typeof person.is_private === "boolean") return person.is_private;
  return person.living_status === "living" || person.living_status === "unknown";
}

/** A name form as the API accepts it (`NameFormIn`; unknown fields are rejected). */
export interface NameFormBody {
  given?: string;
  apellido_paterno?: string;
  apellido_materno?: string;
  particles?: { paterno?: string; materno?: string };
  nombre_usado?: string;
  nicknames: string[];
  surname_order?: SurnameOrder;
  name_type?: string;
  is_primary?: boolean;
}

/** Request body for POST /v1/spaces/{space_id}/people (unknown fields are rejected by the API). */
export interface PersonCreateBody {
  sex: Sex;
  names: NameFormBody[];
}

/** Request body for PATCH /v1/people/{person_id}. `names` replaces every name form. */
export interface PersonPatchBody {
  sex?: Sex;
  names?: NameFormBody[];
}

export type EventParticipantRole = "principal" | "spouse";

/** Request body for POST /v1/spaces/{space_id}/events: free text (`date_original`) or GEDCOM 7. */
export interface EventCreateBody {
  type: string;
  date_original?: string;
  date_value?: string;
  description?: string;
  participants: Array<{ person_id: string; role: EventParticipantRole }>;
}

/** Request body for PATCH /v1/events/{event_id}. */
export interface EventPatchBody {
  date_original?: string;
  description?: string;
}

export type RelationshipType = "parent_child" | "union";
export const PEDIGREES = ["birth", "adopted", "foster", "step"] as const;
export const PARTNER_STATUSES = ["married", "union_libre", "partner", "separated", "divorced"] as const;
export type Pedigree = (typeof PEDIGREES)[number];
export type PartnerStatus = (typeof PARTNER_STATUSES)[number];

/** Request body for POST /v1/spaces/{space_id}/relationships. For parent_child, from = parent. */
export interface RelationshipCreateBody {
  type: RelationshipType;
  from_person_id: string;
  to_person_id: string;
  qualifier: Pedigree | PartnerStatus;
}

/** Request body for POST /v1/spaces/{space_id}/associations (addendum D). */
export interface AssociationCreateBody {
  event_id: string;
  person_id: string;
  role: AssociationRole;
  phrase?: string;
}

export interface WaitlistBody {
  email: string;
  locale: "es" | "en";
  consent: true;
  aviso_version: string;
}
