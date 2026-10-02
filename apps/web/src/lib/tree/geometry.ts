/**
 * Geometry for drawing a `TreeLayout` as SVG, and the camera maths for pan and zoom. Pure, so
 * the drawing and the gestures are unit-tested without a browser.
 */
import type { Pedigree } from "@/lib/api/schemas";

import type { LayoutEdge, LayoutNode, TreeLayout } from "./layout";

export const CARD_WIDTH = 168;
export const CARD_HEIGHT = 72;
export const COLUMN_WIDTH = CARD_WIDTH + 24;
export const ROW_HEIGHT = CARD_HEIGHT + 56;
export const PADDING = 24;

export interface Point {
  x: number;
  y: number;
}

export function nodeOrigin(node: Pick<LayoutNode, "column" | "row">): Point {
  return { x: PADDING + node.column * COLUMN_WIDTH, y: PADDING + node.row * ROW_HEIGHT };
}

export function contentSize(layout: Pick<TreeLayout, "columns" | "rows">): { width: number; height: number } {
  return {
    width: PADDING * 2 + Math.max(0, layout.columns - 1) * COLUMN_WIDTH + CARD_WIDTH,
    height: PADDING * 2 + Math.max(0, layout.rows - 1) * ROW_HEIGHT + CARD_HEIGHT,
  };
}

/** Line styles per pedigree: solid, dashed, dotted and dash-dot, so colour is never the only cue. */
export const PEDIGREE_DASH: Readonly<Record<Pedigree, string | undefined>> = {
  birth: undefined,
  adopted: "8 5",
  foster: "2 4",
  step: "10 4 2 4",
};

/**
 * The SVG path for an edge, as orthogonal segments between card edges. Parents are always on a
 * row above their children (the ancestor layout puts the focus on the bottom row).
 */
export function edgePath(edge: LayoutEdge, nodes: ReadonlyMap<string, LayoutNode>): string | null {
  if (edge.kind === "union") {
    const a = nodes.get(edge.a);
    const b = nodes.get(edge.b);
    if (!a || !b) return null;
    const left = nodeOrigin(a.column <= b.column ? a : b);
    const right = nodeOrigin(a.column <= b.column ? b : a);
    const y = left.y + CARD_HEIGHT / 2;
    return `M ${left.x + CARD_WIDTH} ${y} H ${right.x}`;
  }
  const parent = nodes.get(edge.parent);
  const child = nodes.get(edge.child);
  if (!parent || !child) return null;
  const parentBox = nodeOrigin(parent);
  const childBox = nodeOrigin(child);
  const coParent = edge.coParent ? nodes.get(edge.coParent) : undefined;
  // From the middle of the couple's union line when there is a co-parent, else from the card.
  const start: Point = coParent
    ? {
        x: (parentBox.x + CARD_WIDTH + nodeOrigin(coParent).x) / 2,
        y: parentBox.y + CARD_HEIGHT / 2,
      }
    : { x: parentBox.x + CARD_WIDTH / 2, y: parentBox.y + CARD_HEIGHT };
  const end: Point = { x: childBox.x + CARD_WIDTH / 2, y: childBox.y };
  const mid = (Math.max(start.y, parentBox.y + CARD_HEIGHT) + end.y) / 2;
  return `M ${start.x} ${start.y} V ${mid} H ${end.x} V ${end.y}`;
}

export interface Camera {
  /** Centre of the view, in content units. */
  cx: number;
  cy: number;
  /** Visible width, in content units (smaller is closer). */
  width: number;
}

export const MIN_VIEW_WIDTH = CARD_WIDTH * 1.4;

export function clampWidth(width: number, content: { width: number }): number {
  const max = Math.max(content.width * 1.5, MIN_VIEW_WIDTH * 2);
  return Math.min(max, Math.max(MIN_VIEW_WIDTH, width));
}

function clampAxis(centre: number, span: number, total: number): number {
  if (span >= total) return total / 2;
  return Math.min(total - span / 2, Math.max(span / 2, centre));
}

/**
 * The first view: about one content unit per CSS pixel (never wider than the tree), as close to
 * centred on the focus as the tree's edges allow, so no half of the frame starts empty.
 */
export function initialCamera(
  focus: Point,
  content: { width: number; height: number },
  viewportWidth: number,
  aspect = 1,
): Camera {
  const width = clampWidth(Math.min(content.width, Math.max(MIN_VIEW_WIDTH * 1.6, viewportWidth)), content);
  return {
    cx: clampAxis(focus.x + CARD_WIDTH / 2, width, content.width),
    cy: clampAxis(focus.y + CARD_HEIGHT / 2, width * aspect, content.height),
    width,
  };
}

export function viewBox(camera: Camera, aspect: number): string {
  const height = camera.width * aspect;
  return `${camera.cx - camera.width / 2} ${camera.cy - height / 2} ${camera.width} ${height}`;
}

/** Moves the camera by a drag of (dx, dy) CSS pixels on a viewport `viewportWidth` pixels wide. */
export function pan(camera: Camera, dx: number, dy: number, viewportWidth: number): Camera {
  const scale = camera.width / Math.max(1, viewportWidth);
  return { ...camera, cx: camera.cx - dx * scale, cy: camera.cy - dy * scale };
}

/**
 * Zooms by `factor` (> 1 is closer) keeping the content point under `anchor` still. `anchor` is
 * in viewport fractions (0..1 across, 0..1 down).
 */
export function zoom(
  camera: Camera,
  factor: number,
  content: { width: number },
  aspect: number,
  anchor: Point = { x: 0.5, y: 0.5 },
): Camera {
  const width = clampWidth(camera.width / factor, content);
  const height = camera.width * aspect;
  const newHeight = width * aspect;
  const px = camera.cx - camera.width / 2 + anchor.x * camera.width;
  const py = camera.cy - height / 2 + anchor.y * height;
  return {
    width,
    cx: px - anchor.x * width + width / 2,
    cy: py - anchor.y * newHeight + newHeight / 2,
  };
}

/** Shortens a name to fit a card, keeping the full name for the accessible title. */
export function fitName(name: string, max = 22): string {
  return name.length <= max ? name : `${name.slice(0, max - 1).trimEnd()}…`;
}
