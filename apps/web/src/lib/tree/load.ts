/**
 * Server-side loading of the people around a focus person. The v1 API has no graph endpoint
 * yet (docs/lanes/integration-web.md, contract requests), so this walks `GET /v1/people/{id}`
 * level by level: parents upward, children and partners downward, with a cap on how many
 * people one page may fetch. A failed fetch of a relative is reported, never hidden.
 */
import "server-only";

import type { ApiClient } from "@/lib/api/client";
import { getPerson } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Person } from "@/lib/api/schemas";

export interface NeighbourhoodOptions {
  up: number;
  down: number;
  maxPeople: number;
  concurrency?: number;
}

export interface Neighbourhood {
  people: Person[];
  /** True when the cap stopped the walk before every relative was fetched. */
  truncated: boolean;
  /** Relatives that could not be fetched (each one is a visible notice). */
  failed: number;
}

export function parentIds(person: Person): string[] {
  return person.relationships
    .filter((link) => link.type === "parent_child" && link.to_person_id === person.id)
    .map((link) => link.from_person_id);
}

export function childIds(person: Person): string[] {
  return person.relationships
    .filter((link) => link.type === "parent_child" && link.from_person_id === person.id)
    .map((link) => link.to_person_id);
}

export function partnerIds(person: Person): string[] {
  return person.relationships
    .filter((link) => link.type === "union")
    .map((link) => (link.from_person_id === person.id ? link.to_person_id : link.from_person_id));
}

export function relatedIds(person: Person): string[] {
  return [...new Set([...parentIds(person), ...childIds(person), ...partnerIds(person)])].filter((id) => id !== person.id);
}

async function mapLimited<T, R>(items: readonly T[], limit: number, task: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array<R>(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next;
      next += 1;
      results[index] = await task(items[index] as T);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

/** Fetches several people by id; ones that fail are counted, and auth failures are rethrown. */
export async function fetchPeople(
  api: ApiClient,
  ids: readonly string[],
  concurrency = 6,
): Promise<{ people: Person[]; failed: number }> {
  let failed = 0;
  const fetched = await mapLimited(ids, concurrency, async (id) => {
    try {
      return await getPerson(api, id);
    } catch (error) {
      if (isApiError(error) && (error.code === "unauthorized" || error.code === "early_access_required")) throw error;
      if (!isApiError(error)) throw error;
      failed += 1;
      return null;
    }
  });
  return { people: fetched.filter((person): person is Person => person !== null), failed };
}

export async function loadNeighbourhood(api: ApiClient, focus: Person, options: NeighbourhoodOptions): Promise<Neighbourhood> {
  const byId = new Map<string, Person>([[focus.id, focus]]);
  let truncated = false;
  let failed = 0;

  async function fetchMissing(ids: string[]): Promise<Person[]> {
    const wanted = [...new Set(ids)].filter((id) => !byId.has(id));
    const room = options.maxPeople - byId.size;
    if (wanted.length > room) truncated = true;
    const result = await fetchPeople(api, wanted.slice(0, Math.max(0, room)), options.concurrency);
    failed += result.failed;
    for (const person of result.people) byId.set(person.id, person);
    return result.people;
  }

  // Upward: parents of every parent fetched so far.
  let frontier = [focus];
  for (let level = 0; level < options.up && frontier.length > 0; level += 1) {
    frontier = await fetchMissing(frontier.flatMap(parentIds));
  }

  // Downward: children continue the walk. Partners, and the other parent of each child, are
  // fetched for their names and for grouping children by couple, but are not walked further.
  frontier = [focus];
  for (let level = 0; level < options.down && frontier.length > 0; level += 1) {
    const children = new Set(frontier.flatMap(childIds));
    const companions = frontier.flatMap((person) => [...partnerIds(person), ...(person === focus ? [] : parentIds(person))]);
    await fetchMissing([...children, ...companions]);
    frontier = [...children].map((id) => byId.get(id)).filter((person): person is Person => person !== undefined);
  }
  if (frontier.length > 0) await fetchMissing(frontier.flatMap((person) => [...partnerIds(person), ...parentIds(person)]));

  return { people: [...byId.values()], truncated, failed };
}
