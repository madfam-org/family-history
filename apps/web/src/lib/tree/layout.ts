/**
 * Tree layout around a focus person, as pure functions over a `FamilyGraph`.
 *
 * - `layoutAncestors`: the pedigree. Every parent link counts (birth, adopted, foster, step), so
 *   an adopted child shows both families. Leaves take consecutive columns; a person sits centred
 *   over their parents. The focus is on the bottom row.
 * - `layoutDescendants`: the focus on the top row with every partner beside them; children hang
 *   from the couple they belong to (or from the person alone when the other parent is unknown).
 *
 * A person reached twice (pedigree collapse, cousins who married) is drawn once in full and then
 * as a `repeated` stub, so the walk always terminates. Coordinates are in grid units (column,
 * row); the renderer scales them. Each function also returns an outline, the nested list that
 * serves as the accessible alternative to the drawing.
 */
import type { PartnerStatus, Pedigree } from "@/lib/api/schemas";

import { childrenOf, parentsOf, partnersOf, type FamilyGraph } from "./graph";

export type NodeRole = "focus" | "ancestor" | "descendant" | "partner";

export interface LayoutNode {
  key: string;
  personId: string;
  column: number;
  row: number;
  role: NodeRole;
  repeated: boolean;
  /** Children not drawn because the depth limit was reached. */
  hiddenChildren: number;
}

export type LayoutEdge =
  | { kind: "parent"; parent: string; child: string; coParent: string | null; pedigree: Pedigree }
  | { kind: "union"; a: string; b: string; status: PartnerStatus };

export interface OutlineItem {
  personId: string;
  /** How this person relates to the item above it in the outline. */
  link: { kind: "parent" | "child"; pedigree: Pedigree } | { kind: "partner"; status: PartnerStatus } | null;
  repeated: boolean;
  children: OutlineItem[];
}

export interface TreeLayout {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  columns: number;
  rows: number;
  outline: OutlineItem;
}

class Builder {
  readonly nodes: LayoutNode[] = [];
  readonly edges: LayoutEdge[] = [];
  readonly expanded = new Set<string>();
  nextColumn = 0;

  add(node: Omit<LayoutNode, "key">): LayoutNode {
    const full = { ...node, key: `n${this.nodes.length}` };
    this.nodes.push(full);
    return full;
  }

  shift(fromIndex: number, by: number): void {
    if (by === 0) return;
    for (let index = fromIndex; index < this.nodes.length; index += 1) {
      const node = this.nodes[index];
      if (node) node.column += by;
    }
  }

  result(outline: OutlineItem, flipRows: boolean): TreeLayout {
    const maxRow = this.nodes.reduce((max, node) => Math.max(max, node.row), 0);
    if (flipRows) for (const node of this.nodes) node.row = maxRow - node.row;
    const minColumn = this.nodes.reduce((min, node) => Math.min(min, node.column), Infinity);
    if (Number.isFinite(minColumn) && minColumn !== 0) for (const node of this.nodes) node.column -= minColumn;
    const columns = this.nodes.reduce((max, node) => Math.max(max, node.column + 1), 0);
    return { nodes: this.nodes, edges: this.edges, columns, rows: maxRow + 1, outline };
  }
}

export function layoutAncestors(graph: FamilyGraph, focus: string, maxDepth = 4): TreeLayout {
  const builder = new Builder();

  function visit(personId: string, depth: number, role: NodeRole): { node: LayoutNode; outline: OutlineItem } {
    const repeated = builder.expanded.has(personId);
    const parents = repeated || depth >= maxDepth ? [] : parentsOf(graph, personId);
    builder.expanded.add(personId);
    if (parents.length === 0) {
      const hidden = !repeated && depth >= maxDepth ? parentsOf(graph, personId).length : 0;
      const node = builder.add({ personId, column: builder.nextColumn, row: depth, role, repeated, hiddenChildren: hidden });
      builder.nextColumn += 1;
      return { node, outline: { personId, link: null, repeated, children: [] } };
    }
    const visited = parents.map((parent) => ({ parent, ...visit(parent.id, depth + 1, "ancestor") }));
    const first = visited[0]?.node.column ?? 0;
    const last = visited[visited.length - 1]?.node.column ?? first;
    const node = builder.add({ personId, column: (first + last) / 2, row: depth, role, repeated, hiddenChildren: 0 });
    for (const { parent, node: parentNode } of visited) {
      builder.edges.push({ kind: "parent", parent: parentNode.key, child: node.key, coParent: null, pedigree: parent.pedigree });
    }
    const children = visited.map(({ parent, outline }) => ({
      ...outline,
      link: { kind: "parent" as const, pedigree: parent.pedigree },
    }));
    return { node, outline: { personId, link: null, repeated, children } };
  }

  const { outline } = visit(focus, 0, "focus");
  return builder.result(outline, true);
}

interface ChildGroup {
  partner: string | null;
  status: PartnerStatus | null;
  children: Array<{ id: string; pedigree: Pedigree }>;
}

/** Children grouped by their other parent; recorded partners first, even without children. */
export function childGroups(graph: FamilyGraph, personId: string): ChildGroup[] {
  const groups = new Map<string | null, ChildGroup>();
  for (const partner of partnersOf(graph, personId)) {
    groups.set(partner.id, { partner: partner.id, status: partner.status, children: [] });
  }
  for (const child of childrenOf(graph, personId)) {
    const others = parentsOf(graph, child.id).filter((parent) => parent.id !== personId);
    const other = others.find((parent) => groups.has(parent.id))?.id ?? others[0]?.id ?? null;
    if (!groups.has(other)) groups.set(other, { partner: other, status: null, children: [] });
    groups.get(other)?.children.push(child);
  }
  const ordered = [...groups.values()];
  return [...ordered.filter((group) => group.partner !== null), ...ordered.filter((group) => group.partner === null)];
}

export function layoutDescendants(graph: FamilyGraph, focus: string, maxDepth = 3): TreeLayout {
  const builder = new Builder();

  function visit(personId: string, depth: number, role: NodeRole): { node: LayoutNode; outline: OutlineItem } {
    const repeated = builder.expanded.has(personId);
    builder.expanded.add(personId);
    const groups = repeated ? [] : childGroups(graph, personId);
    const expand = depth < maxDepth;
    const startIndex = builder.nodes.length;
    const startColumn = builder.nextColumn;

    const laidOut = groups.map((group) => ({
      group,
      children: expand ? group.children.map((child) => ({ child, ...visit(child.id, depth + 1, "descendant") })) : [],
    }));
    const childColumns = laidOut.flatMap(({ children }) => children.map(({ node }) => node.column));
    const partners = groups.filter((group) => group.partner !== null);
    const rowWidth = 1 + partners.length;

    let column: number;
    if (childColumns.length === 0) {
      column = builder.nextColumn;
    } else {
      const centre = (Math.min(...childColumns) + Math.max(...childColumns)) / 2;
      column = centre - (rowWidth - 1) / 2;
      if (column < startColumn) {
        builder.shift(startIndex, startColumn - column);
        column = startColumn;
      }
    }
    const hidden = expand ? 0 : groups.reduce((sum, group) => sum + group.children.length, 0);
    const node = builder.add({ personId, column, row: depth, role, repeated, hiddenChildren: hidden });
    const partnerNodes = new Map<string, LayoutNode>();
    partners.forEach((group, index) => {
      const partnerId = group.partner as string;
      const partnerNode = builder.add({
        personId: partnerId,
        column: column + index + 1,
        row: depth,
        role: "partner",
        repeated: false,
        hiddenChildren: 0,
      });
      partnerNodes.set(partnerId, partnerNode);
      builder.edges.push({ kind: "union", a: node.key, b: partnerNode.key, status: group.status ?? "partner" });
    });
    builder.nextColumn = Math.max(builder.nextColumn, column + rowWidth);

    const outlineChildren: OutlineItem[] = [];
    for (const { group, children } of laidOut) {
      const coParent = group.partner ? (partnerNodes.get(group.partner)?.key ?? null) : null;
      for (const { child, node: childNode } of children) {
        builder.edges.push({ kind: "parent", parent: node.key, child: childNode.key, coParent, pedigree: child.pedigree });
      }
      const childItems = children.map(({ child, outline }) => ({
        ...outline,
        link: { kind: "child" as const, pedigree: child.pedigree },
      }));
      if (group.partner) {
        outlineChildren.push({
          personId: group.partner,
          link: { kind: "partner", status: group.status ?? "partner" },
          repeated: false,
          children: childItems,
        });
      } else {
        outlineChildren.push(...childItems);
      }
    }
    return { node, outline: { personId, link: null, repeated, children: outlineChildren } };
  }

  const { outline } = visit(focus, 0, "focus");
  return builder.result(outline, false);
}
