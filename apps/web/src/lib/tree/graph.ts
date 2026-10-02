/**
 * The family graph the tree view draws: people plus parent and partner links. Built from the
 * API's `Person` records (each carries its own relationships); a graph, not a tree, so
 * remarriages, adoptions and pedigree collapse are all representable. Pure.
 */
import { displayDate } from "@/lib/dates/hints";
import {
  isPrivatePerson,
  PARTNER_STATUSES,
  PEDIGREES,
  type LivingStatus,
  type PartnerStatus,
  type Pedigree,
  type Person,
  type Sex,
} from "@/lib/api/schemas";

export interface TreePerson {
  id: string;
  name: string;
  sex: Sex;
  livingStatus: LivingStatus;
  isPrivate: boolean;
  birth: string | null;
  death: string | null;
}

export interface ParentLink {
  parent: string;
  child: string;
  pedigree: Pedigree;
}

export interface PartnerLink {
  a: string;
  b: string;
  status: PartnerStatus;
}

export interface FamilyGraph {
  people: ReadonlyMap<string, TreePerson>;
  parentLinks: readonly ParentLink[];
  partnerLinks: readonly PartnerLink[];
}

export function asPedigree(value: string | null | undefined): Pedigree {
  return (PEDIGREES as readonly string[]).includes(value ?? "") ? (value as Pedigree) : "birth";
}

export function asPartnerStatus(value: string | null | undefined): PartnerStatus {
  return (PARTNER_STATUSES as readonly string[]).includes(value ?? "") ? (value as PartnerStatus) : "partner";
}

function vitalDate(person: Person, type: "birth" | "death", locale: "es" | "en"): string | null {
  const brief = person[type];
  if (brief) return displayDate(brief, locale);
  const event = person.events.find((candidate) => candidate.type === type);
  return event ? displayDate(event, locale) : null;
}

export function toTreePerson(person: Person, locale: "es" | "en"): TreePerson {
  return {
    id: person.id,
    name: person.display_name,
    sex: person.sex,
    livingStatus: person.living_status,
    isPrivate: isPrivatePerson(person),
    birth: vitalDate(person, "birth", locale),
    death: vitalDate(person, "death", locale),
  };
}

/** Builds the graph from fetched people. Links to people that were not fetched are dropped. */
export function buildGraph(persons: readonly Person[], locale: "es" | "en"): FamilyGraph {
  const people = new Map(persons.map((person) => [person.id, toTreePerson(person, locale)]));
  const seen = new Set<string>();
  const parentLinks: ParentLink[] = [];
  const partnerLinks: PartnerLink[] = [];
  for (const person of persons) {
    for (const link of person.relationships) {
      if (seen.has(link.id)) continue;
      seen.add(link.id);
      if (!people.has(link.from_person_id) || !people.has(link.to_person_id)) continue;
      if (link.type === "parent_child") {
        parentLinks.push({ parent: link.from_person_id, child: link.to_person_id, pedigree: asPedigree(link.qualifier) });
      } else if (link.type === "union") {
        partnerLinks.push({ a: link.from_person_id, b: link.to_person_id, status: asPartnerStatus(link.qualifier) });
      }
    }
  }
  return { people, parentLinks, partnerLinks };
}

const PEDIGREE_ORDER: Readonly<Record<Pedigree, number>> = { birth: 0, adopted: 1, foster: 2, step: 3 };
const SEX_ORDER: Readonly<Record<Sex, number>> = { M: 0, F: 1, X: 2, U: 3 };

function byName(graph: FamilyGraph) {
  return (a: string, b: string) => (graph.people.get(a)?.name ?? a).localeCompare(graph.people.get(b)?.name ?? b, "es");
}

/** Parents, birth parents first, then adoptive, foster and step; father before mother. */
export function parentsOf(graph: FamilyGraph, child: string): Array<{ id: string; pedigree: Pedigree }> {
  const name = byName(graph);
  return graph.parentLinks
    .filter((link) => link.child === child)
    .map((link) => ({ id: link.parent, pedigree: link.pedigree }))
    .sort(
      (a, b) =>
        PEDIGREE_ORDER[a.pedigree] - PEDIGREE_ORDER[b.pedigree] ||
        SEX_ORDER[graph.people.get(a.id)?.sex ?? "U"] - SEX_ORDER[graph.people.get(b.id)?.sex ?? "U"] ||
        name(a.id, b.id),
    );
}

export function childrenOf(graph: FamilyGraph, parent: string): Array<{ id: string; pedigree: Pedigree }> {
  const name = byName(graph);
  return graph.parentLinks
    .filter((link) => link.parent === parent)
    .map((link) => ({ id: link.child, pedigree: link.pedigree }))
    .sort((a, b) => name(a.id, b.id));
}

const STATUS_ORDER: Readonly<Record<PartnerStatus, number>> = {
  married: 0,
  union_libre: 1,
  partner: 2,
  separated: 3,
  divorced: 4,
};

export function partnersOf(graph: FamilyGraph, person: string): Array<{ id: string; status: PartnerStatus }> {
  const name = byName(graph);
  const out = new Map<string, PartnerStatus>();
  for (const link of graph.partnerLinks) {
    const other = link.a === person ? link.b : link.b === person ? link.a : null;
    if (other && other !== person && !out.has(other)) out.set(other, link.status);
  }
  return [...out]
    .map(([id, status]) => ({ id, status }))
    .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || name(a.id, b.id));
}
