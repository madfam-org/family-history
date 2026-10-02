/** One function per v1 endpoint the web app uses. */
import { z } from "zod";

import type { ApiClient } from "./client";
import {
  meSchema,
  peoplePageSchema,
  personEventSchema,
  personSchema,
  relationshipSchema,
  spaceSchema,
  spaceSummarySchema,
  type AssociationCreateBody,
  type EventCreateBody,
  type EventPatchBody,
  type Me,
  type PeoplePage,
  type Person,
  type PersonCreateBody,
  type PersonEvent,
  type PersonPatchBody,
  type Relationship,
  type RelationshipCreateBody,
  type Space,
  type SpaceSummary,
  type WaitlistBody,
} from "./schemas";
import {
  compadrazgoSchema,
  createdAssociationSchema,
  jobAcceptedSchema,
  jobSchema,
  kinshipSchema,
  type Compadrazgo,
  type ExportFormat,
  type Job,
  type Kinship,
} from "./schemas-family";

export const PEOPLE_PAGE_SIZE = 50;

const segment = (value: string) => encodeURIComponent(value);

export function getMe(api: ApiClient): Promise<Me> {
  return api.json("/v1/me", meSchema);
}

export function listSpaces(api: ApiClient): Promise<SpaceSummary[]> {
  return api.json("/v1/spaces", z.array(spaceSummarySchema));
}

export function createSpace(api: ApiClient, name: string): Promise<Space> {
  return api.json("/v1/spaces", spaceSchema, { method: "POST", body: { name } });
}

export function listPeople(
  api: ApiClient,
  spaceId: string,
  params: { q?: string | undefined; cursor?: string | undefined; limit?: number } = {},
): Promise<PeoplePage> {
  return api.json(`/v1/spaces/${segment(spaceId)}/people`, peoplePageSchema, {
    query: { q: params.q, cursor: params.cursor, limit: params.limit ?? PEOPLE_PAGE_SIZE },
  });
}

export function createPerson(api: ApiClient, spaceId: string, body: PersonCreateBody): Promise<Person> {
  return api.json(`/v1/spaces/${segment(spaceId)}/people`, personSchema, { method: "POST", body });
}

const eventSchema = personEventSchema.extend({ id: z.string() });

export function createEvent(api: ApiClient, spaceId: string, body: EventCreateBody): Promise<PersonEvent> {
  return api.json(`/v1/spaces/${segment(spaceId)}/events`, eventSchema, { method: "POST", body });
}

export function patchEvent(api: ApiClient, eventId: string, body: EventPatchBody): Promise<PersonEvent> {
  return api.json(`/v1/events/${segment(eventId)}`, eventSchema, { method: "PATCH", body });
}

export function patchPerson(api: ApiClient, personId: string, body: PersonPatchBody): Promise<Person> {
  return api.json(`/v1/people/${segment(personId)}`, personSchema, { method: "PATCH", body });
}

export function createRelationship(
  api: ApiClient,
  spaceId: string,
  body: RelationshipCreateBody,
): Promise<Relationship> {
  return api.json(`/v1/spaces/${segment(spaceId)}/relationships`, relationshipSchema, { method: "POST", body });
}

export function deleteRelationship(api: ApiClient, relationshipId: string): Promise<number> {
  return api.empty(`/v1/relationships/${segment(relationshipId)}`, { method: "DELETE" });
}

/** Addendum D: what `otherId` is to `personId`. A 404 `no_relation` means none was found. */
export function getKinship(api: ApiClient, personId: string, otherId: string): Promise<Kinship> {
  return api.json(`/v1/people/${segment(personId)}/kinship`, kinshipSchema, { query: { to: otherId } });
}

export function getCompadrazgo(api: ApiClient, personId: string): Promise<Compadrazgo> {
  return api.json(`/v1/people/${segment(personId)}/compadrazgo`, compadrazgoSchema);
}

export function createAssociation(
  api: ApiClient,
  spaceId: string,
  body: AssociationCreateBody,
): Promise<{ id: string }> {
  return api.json(`/v1/spaces/${segment(spaceId)}/associations`, createdAssociationSchema, {
    method: "POST",
    body,
  });
}

export function deleteAssociation(api: ApiClient, associationId: string): Promise<number> {
  return api.empty(`/v1/associations/${segment(associationId)}`, { method: "DELETE" });
}

export const IMPORT_MAX_BYTES = 25 * 1024 * 1024;
const UPLOAD_TIMEOUT_MS = 120_000;

/** Addendum E: streams a multipart upload (field `file`) through to the API; 202 `{job_id}`. */
export function startImport(
  api: ApiClient,
  spaceId: string,
  upload: { stream: ReadableStream<Uint8Array>; contentType: string },
): Promise<{ job_id: string }> {
  return api.json(`/v1/spaces/${segment(spaceId)}/imports`, jobAcceptedSchema, {
    method: "POST",
    raw: upload,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
}

/** Addendum E: free for everyone, never gated by plan. */
export function startExport(api: ApiClient, spaceId: string, format: ExportFormat): Promise<{ job_id: string }> {
  return api.json(`/v1/spaces/${segment(spaceId)}/exports`, jobAcceptedSchema, {
    method: "POST",
    body: { format },
  });
}

export function getJob(api: ApiClient, jobId: string): Promise<Job> {
  return api.json(`/v1/jobs/${segment(jobId)}`, jobSchema);
}

/** The finished file. 410 (`download_expired`) after 24 hours. */
export function downloadJob(api: ApiClient, jobId: string): Promise<Response> {
  return api.stream(`/v1/jobs/${segment(jobId)}/download`, { accept: "*/*", timeoutMs: UPLOAD_TIMEOUT_MS });
}

export function getPerson(api: ApiClient, personId: string): Promise<Person> {
  return api.json(`/v1/people/${segment(personId)}`, personSchema);
}

/** Public and rate-limited; the API answers 202 with no body. */
export function joinWaitlist(api: ApiClient, body: WaitlistBody): Promise<number> {
  return api.empty("/v1/waitlist", { method: "POST", body });
}
