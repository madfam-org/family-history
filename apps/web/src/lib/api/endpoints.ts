/** One function per v1 endpoint the web app uses. */
import { z } from "zod";

import type { ApiClient } from "./client";
import {
  meSchema,
  peoplePageSchema,
  personSchema,
  spaceSchema,
  spaceSummarySchema,
  type EventCreateBody,
  type Me,
  type PeoplePage,
  type Person,
  type PersonCreateBody,
  type Space,
  type SpaceSummary,
  type WaitlistBody,
} from "./schemas";

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

/** Creates an event; the response is not needed by the web app, only its success. */
export function createEvent(api: ApiClient, spaceId: string, body: EventCreateBody): Promise<number> {
  return api.empty(`/v1/spaces/${segment(spaceId)}/events`, { method: "POST", body });
}

export function getPerson(api: ApiClient, personId: string): Promise<Person> {
  return api.json(`/v1/people/${segment(personId)}`, personSchema);
}

/** Public and rate-limited; the API answers 202 with no body. */
export function joinWaitlist(api: ApiClient, body: WaitlistBody): Promise<number> {
  return api.empty("/v1/waitlist", { method: "POST", body });
}
