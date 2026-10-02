/**
 * Zod schemas for the v1 API contract (docs/ARCHITECTURE.md §"v1 API used by the web app").
 * Fixed shapes (SpaceSummary, PersonSummary, EventBrief, Me) are strict about the fields the
 * UI relies on. The full Person shape is not fixed by the contract yet, so its nested parts
 * are tolerant: unknown fields pass through and missing collections default to empty.
 */
import { z } from "zod";

export const roleSchema = z.enum(["steward", "editor", "contributor", "viewer"]);
export const sexSchema = z.enum(["M", "F", "X", "U"]);
export const livingStatusSchema = z.enum(["living", "deceased", "unknown"]);
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

export const eventBriefSchema = z.object({
  date_value: z.string().nullable(),
  place: z.string().nullable(),
});

export const personSummarySchema = z.object({
  id: z.string(),
  display_name: z.string(),
  sex: sexSchema,
  living_status: livingStatusSchema,
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

export const nameFormSchema = z
  .object({
    id: z.string().optional(),
    given: optionalText,
    surname_paternal: optionalText,
    surname_maternal: optionalText,
    nickname: optionalText,
    nicknames: z.array(z.string()).optional(),
    display: optionalText,
    type: optionalText,
  })
  .loose();

export const personEventSchema = z
  .object({
    id: z.string().optional(),
    type: z.string(),
    date_value: optionalText,
    date_original: optionalText,
    place: optionalText,
  })
  .loose();

export const relationshipSchema = z
  .object({
    id: z.string(),
    type: z.string(),
    from_person_id: z.string(),
    to_person_id: z.string(),
    qualifier: optionalText,
  })
  .loose();

export const citationSchema = z
  .object({
    id: z.string(),
    title: optionalText,
    detail: optionalText,
  })
  .loose();

export const personSchema = personSummarySchema
  .extend({
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

/** Request body for POST /v1/spaces/{space_id}/people. See docs/lanes/web.md, contract requests. */
export interface PersonCreateBody {
  names: Array<{
    given: string | null;
    surname_paternal: string | null;
    surname_maternal: string | null;
    nicknames: string[];
  }>;
  sex: Sex;
  birth: { date_original: string } | null;
}

export interface WaitlistBody {
  email: string;
  locale: "es" | "en";
  consent: true;
  aviso_version: string;
}
