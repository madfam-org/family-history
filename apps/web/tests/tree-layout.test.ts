/**
 * Tree layout pure functions: the family graph, ancestor and descendant layouts (multiple
 * partners, adoption, foster and step links, pedigree collapse) and the drawing geometry.
 * Synthetic people with names from the domain lexicon.
 */
import { describe, expect, it } from "vitest";

import type { Person } from "@/lib/api/schemas";
import {
  CARD_HEIGHT,
  CARD_WIDTH,
  clampWidth,
  contentSize,
  edgePath,
  fitName,
  initialCamera,
  MIN_VIEW_WIDTH,
  nodeOrigin,
  pan,
  PEDIGREE_DASH,
  viewBox,
  zoom,
} from "@/lib/tree/geometry";
import { buildGraph, childrenOf, parentsOf, partnersOf, type FamilyGraph } from "@/lib/tree/graph";
import { childGroups, layoutAncestors, layoutDescendants, type TreeLayout } from "@/lib/tree/layout";
import { childIds, parentIds, partnerIds, relatedIds } from "@/lib/tree/load";

type Link = [type: "parent_child" | "union", from: string, to: string, qualifier: string];

const NAMES: Record<string, [string, "M" | "F"]> = {
  ego: ["Regina Castillo Ramírez", "F"],
  dad: ["Ignacio Castillo Soto", "M"],
  mom: ["Leticia Ramírez Luna", "F"],
  adoptiveDad: ["Gerardo Vega Ríos", "M"],
  stepMom: ["Yolanda Ortega Lara", "F"],
  gpa: ["Porfirio Castillo Méndez", "M"],
  gma: ["Macaria Soto Ruiz", "F"],
  partner1: ["Emiliano Torres Vega", "M"],
  partner2: ["Mateo Salazar Peña", "M"],
  kid1: ["Romina Torres Castillo", "F"],
  kid2: ["Santiago Torres Castillo", "M"],
  kid3: ["Diego Salazar Castillo", "M"],
  fosterKid: ["Valentina Cruz Díaz", "F"],
};

function people(links: readonly Link[], ids = Object.keys(NAMES)): Person[] {
  return ids.map((id) => {
    const [display_name, sex] = NAMES[id] ?? [id, "U"];
    return {
      id,
      display_name,
      sex,
      living_status: "living",
      visibility: "space",
      birth: id === "ego" ? { date_value: "1990", date_display: { es: "1990", en: "1990" }, place: null } : null,
      death: null,
      names: [],
      events: [],
      citations: [],
      relationships: links
        .map(([type, from, to, qualifier], index) => ({
          id: `r${index}`,
          type,
          from_person_id: from,
          to_person_id: to,
          qualifier,
        }))
        .filter((link) => link.from_person_id === id || link.to_person_id === id),
    } as Person;
  });
}

const LINKS: Link[] = [
  ["parent_child", "dad", "ego", "birth"],
  ["parent_child", "mom", "ego", "birth"],
  ["parent_child", "adoptiveDad", "ego", "adopted"],
  ["parent_child", "stepMom", "ego", "step"],
  ["parent_child", "gpa", "dad", "birth"],
  ["parent_child", "gma", "dad", "birth"],
  ["union", "dad", "mom", "divorced"],
  ["union", "ego", "partner1", "divorced"],
  ["union", "ego", "partner2", "union_libre"],
  ["parent_child", "ego", "kid1", "birth"],
  ["parent_child", "partner1", "kid1", "birth"],
  ["parent_child", "ego", "kid2", "birth"],
  ["parent_child", "partner1", "kid2", "birth"],
  ["parent_child", "ego", "kid3", "birth"],
  ["parent_child", "partner2", "kid3", "birth"],
  ["parent_child", "ego", "fosterKid", "foster"],
];

const graph: FamilyGraph = buildGraph(people(LINKS), "es");

function nodeOf(layout: TreeLayout, personId: string, repeated = false) {
  return layout.nodes.find((node) => node.personId === personId && node.repeated === repeated);
}

describe("family graph", () => {
  it("keeps each relationship once and drops links to people not fetched", () => {
    expect(graph.parentLinks).toHaveLength(13);
    expect(graph.partnerLinks).toHaveLength(3);
    const partial = buildGraph(people(LINKS, ["ego", "dad"]), "es");
    expect(partial.parentLinks).toEqual([{ parent: "dad", child: "ego", pedigree: "birth" }]);
    expect(partial.people.get("ego")?.birth).toBe("1990");
  });

  it("orders parents birth first, then adoptive, then step; father before mother", () => {
    expect(parentsOf(graph, "ego").map((parent) => `${parent.id}:${parent.pedigree}`)).toEqual([
      "dad:birth",
      "mom:birth",
      "adoptiveDad:adopted",
      "stepMom:step",
    ]);
  });

  it("lists partners by status and children by name", () => {
    expect(partnersOf(graph, "ego").map((partner) => partner.id)).toEqual(["partner2", "partner1"]);
    expect(childrenOf(graph, "ego").map((child) => child.id)).toEqual(["kid3", "kid1", "kid2", "fosterKid"]);
  });

  it("marks living people private (no is_private from the API)", () => {
    expect(graph.people.get("ego")?.isPrivate).toBe(true);
  });

  it("reads parent, child and partner ids from a person's relationships", () => {
    const [ego] = people(LINKS, ["ego"]);
    expect(parentIds(ego as Person).sort()).toEqual(["adoptiveDad", "dad", "mom", "stepMom"]);
    expect(childIds(ego as Person).sort()).toEqual(["fosterKid", "kid1", "kid2", "kid3"]);
    expect(partnerIds(ego as Person).sort()).toEqual(["partner1", "partner2"]);
    expect(relatedIds(ego as Person)).toHaveLength(10);
  });
});

describe("ancestor layout", () => {
  const layout = layoutAncestors(graph, "ego", 4);

  it("puts the focus on the bottom row and every parent link above it", () => {
    const ego = nodeOf(layout, "ego");
    expect(ego?.role).toBe("focus");
    expect(ego?.row).toBe(layout.rows - 1);
    for (const id of ["dad", "mom", "adoptiveDad", "stepMom"]) expect(nodeOf(layout, id)?.row).toBe(layout.rows - 2);
    expect(nodeOf(layout, "gpa")?.row).toBe(0);
  });

  it("keeps the pedigree on each edge", () => {
    const pedigrees = layout.edges.flatMap((edge) => (edge.kind === "parent" ? [edge.pedigree] : []));
    expect(pedigrees.sort()).toEqual(["adopted", "birth", "birth", "birth", "birth", "step"]);
  });

  it("centres a person over their parents and never overlaps two cards", () => {
    const dad = nodeOf(layout, "dad");
    expect(dad?.column).toBe(((nodeOf(layout, "gpa")?.column ?? 0) + (nodeOf(layout, "gma")?.column ?? 0)) / 2);
    const taken = new Set(layout.nodes.map((node) => `${node.row}:${node.column}`));
    expect(taken.size).toBe(layout.nodes.length);
    expect(Math.min(...layout.nodes.map((node) => node.column))).toBe(0);
  });

  it("draws a person reached twice once in full, then as a stub (pedigree collapse)", () => {
    const cousins: Link[] = [
      ["parent_child", "dad", "ego", "birth"],
      ["parent_child", "mom", "ego", "birth"],
      ["parent_child", "gpa", "dad", "birth"],
      ["parent_child", "gpa", "mom", "birth"],
      ["parent_child", "gma", "gpa", "birth"],
    ];
    const collapsed = layoutAncestors(buildGraph(people(cousins), "es"), "ego", 4);
    expect(collapsed.nodes.filter((node) => node.personId === "gpa")).toHaveLength(2);
    expect(nodeOf(collapsed, "gpa", true)).toBeDefined();
    expect(collapsed.nodes.filter((node) => node.personId === "gma")).toHaveLength(1);
  });

  it("stops at the depth limit and counts what it hid", () => {
    const shallow = layoutAncestors(graph, "ego", 1);
    expect(nodeOf(shallow, "gpa")).toBeUndefined();
    expect(nodeOf(shallow, "dad")?.hiddenChildren).toBe(2);
  });

  it("returns an outline with the same people and relations", () => {
    expect(layout.outline.personId).toBe("ego");
    expect(layout.outline.children.map((child) => child.link)).toEqual([
      { kind: "parent", pedigree: "birth" },
      { kind: "parent", pedigree: "birth" },
      { kind: "parent", pedigree: "adopted" },
      { kind: "parent", pedigree: "step" },
    ]);
  });

  it("is a single node for someone with no parents", () => {
    const alone = layoutAncestors(graph, "kid1", 4);
    expect(alone.nodes.filter((node) => node.personId === "kid1")).toHaveLength(1);
  });
});

describe("descendant layout", () => {
  const layout = layoutDescendants(graph, "ego", 3);

  it("groups children by the couple they belong to; foster children hang from the person", () => {
    expect(childGroups(graph, "ego").map((group) => [group.partner, group.children.map((child) => child.id)])).toEqual([
      ["partner2", ["kid3"]],
      ["partner1", ["kid1", "kid2"]],
      [null, ["fosterKid"]],
    ]);
  });

  it("puts every partner beside the person, joined by a union edge with its status", () => {
    const ego = nodeOf(layout, "ego");
    const partners = layout.nodes.filter((node) => node.role === "partner");
    expect(partners.map((node) => node.personId).sort()).toEqual(["partner1", "partner2"]);
    for (const partner of partners) expect(partner.row).toBe(ego?.row);
    const unions = layout.edges.flatMap((edge) => (edge.kind === "union" ? [edge.status] : []));
    expect(unions.sort()).toEqual(["divorced", "union_libre"]);
  });

  it("draws each child from its couple, with the pedigree", () => {
    const parentEdges = layout.edges.filter((edge) => edge.kind === "parent");
    expect(parentEdges).toHaveLength(4);
    const foster = parentEdges.find((edge) => edge.kind === "parent" && edge.pedigree === "foster");
    expect(foster && foster.kind === "parent" ? foster.coParent : "missing").toBeNull();
    const withCouple = parentEdges.filter((edge) => edge.kind === "parent" && edge.coParent !== null);
    expect(withCouple).toHaveLength(3);
  });

  it("never overlaps cards and never uses negative columns", () => {
    const taken = new Set(layout.nodes.map((node) => `${node.row}:${node.column}`));
    expect(taken.size).toBe(layout.nodes.length);
    expect(Math.min(...layout.nodes.map((node) => node.column))).toBe(0);
  });

  it("outlines partners with their children under them", () => {
    const [first] = layout.outline.children;
    expect(first?.link).toEqual({ kind: "partner", status: "union_libre" });
    expect(first?.children.map((child) => child.personId)).toEqual(["kid3"]);
    expect(layout.outline.children.at(-1)?.link).toEqual({ kind: "child", pedigree: "foster" });
  });

  it("hides children past the depth limit and says how many", () => {
    const shallow = layoutDescendants(graph, "ego", 0);
    expect(nodeOf(shallow, "kid1")).toBeUndefined();
    expect(nodeOf(shallow, "ego")?.hiddenChildren).toBe(4);
  });
});

describe("drawing geometry", () => {
  const layout = layoutAncestors(graph, "ego", 4);
  const nodes = new Map(layout.nodes.map((node) => [node.key, node]));

  it("sizes the content to the grid", () => {
    const size = contentSize(layout);
    expect(size.width).toBeGreaterThanOrEqual(CARD_WIDTH);
    expect(size.height).toBeGreaterThanOrEqual(CARD_HEIGHT * layout.rows);
  });

  it("draws parent edges from the parent's bottom to the child's top", () => {
    const edge = layout.edges.find((candidate) => candidate.kind === "parent");
    const path = edge ? edgePath(edge, nodes) : null;
    expect(path).toMatch(/^M [\d.]+ [\d.]+ V [\d.]+ H [\d.]+ V [\d.]+$/);
    if (edge?.kind === "parent") {
      const child = nodes.get(edge.child);
      expect(path?.endsWith(`V ${child ? nodeOrigin(child).y : 0}`)).toBe(true);
    }
  });

  it("draws union edges as a horizontal line between the cards", () => {
    const descendants = layoutDescendants(graph, "ego", 1);
    const map = new Map(descendants.nodes.map((node) => [node.key, node]));
    const union = descendants.edges.find((edge) => edge.kind === "union");
    expect(union ? edgePath(union, map) : null).toMatch(/^M [\d.]+ [\d.]+ H [\d.]+$/);
  });

  it("gives every non-birth pedigree its own dash pattern", () => {
    const dashes = [PEDIGREE_DASH.adopted, PEDIGREE_DASH.foster, PEDIGREE_DASH.step];
    expect(PEDIGREE_DASH.birth).toBeUndefined();
    expect(new Set(dashes).size).toBe(3);
  });

  it("starts centred on the focus and never wider than the tree", () => {
    const content = contentSize(layout);
    const camera = initialCamera({ x: 100, y: 50 }, content, 360);
    expect(camera.cx).toBe(100 + CARD_WIDTH / 2);
    expect(camera.width).toBeLessThanOrEqual(Math.max(content.width, MIN_VIEW_WIDTH * 1.6));
    expect(viewBox(camera, 1).split(" ")).toHaveLength(4);
  });

  it("pans by screen pixels scaled to the view and zooms around an anchor", () => {
    const content = { width: 2000, height: 1000 };
    const camera = { cx: 500, cy: 300, width: 1000 };
    expect(pan(camera, 40, -20, 500)).toEqual({ cx: 420, cy: 340, width: 1000 });
    const closer = zoom(camera, 2, content, 0.5);
    expect(closer.width).toBe(500);
    expect(closer.cx).toBe(500);
    const anchored = zoom(camera, 2, content, 0.5, { x: 0, y: 0 });
    expect(anchored.cx - anchored.width / 2).toBe(camera.cx - camera.width / 2);
    expect(clampWidth(1, content)).toBe(MIN_VIEW_WIDTH);
    expect(clampWidth(1e9, content)).toBe(3000);
  });

  it("shortens long names for the card only", () => {
    expect(fitName("María Guadalupe de la Garza Treviño", 22)).toHaveLength(22);
    expect(fitName("Petra Luna")).toBe("Petra Luna");
  });
});
