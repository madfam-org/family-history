"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { TreePerson } from "@/lib/tree/graph";
import {
  CARD_HEIGHT,
  CARD_WIDTH,
  contentSize,
  edgePath,
  fitName,
  initialCamera,
  nodeOrigin,
  pan,
  PEDIGREE_DASH,
  viewBox,
  zoom,
  type Camera,
} from "@/lib/tree/geometry";
import type { LayoutNode, TreeLayout } from "@/lib/tree/layout";

const DRAG_THRESHOLD_PX = 4;
const KEY_PAN_PX = 48;

/**
 * The tree drawing: hand-written SVG (no library), so it renders on the server without
 * browser APIs, needs no inline styles under the strict CSP, and keeps cards as real links.
 * Pan by dragging (one finger or the mouse), pinch or wheel to zoom, or use the buttons and the
 * keyboard. The same content is always available as a list (TreeOutline).
 */
export function TreeCanvas({
  layout,
  people,
  href,
  label,
}: {
  layout: TreeLayout;
  people: Readonly<Record<string, TreePerson>>;
  /** Each card links to `${prefix}${encodeURIComponent(personId)}${suffix}` (props must serialise). */
  href: { prefix: string; suffix: string };
  label: string;
}) {
  const t = useTranslations("family.tree");
  const privacy = useTranslations("family.privacy");
  const content = useMemo(() => contentSize(layout), [layout]);
  const nodes = useMemo(() => new Map(layout.nodes.map((node) => [node.key, node])), [layout]);
  const focus = layout.nodes.find((node) => node.role === "focus") ?? layout.nodes[0];
  const focusPoint = focus ? nodeOrigin(focus) : { x: 0, y: 0 };

  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: content.width, height: content.height });
  const [camera, setCamera] = useState<Camera>(() => initialCamera(focusPoint, content, content.width));
  const placed = useRef(false);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const dragged = useRef(false);
  const aspect = size.height / Math.max(1, size.width);

  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize({ width, height });
      if (!placed.current && width > 0) {
        placed.current = true;
        setCamera(initialCamera(focusPoint, content, width));
      }
    });
    observer.observe(element);
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const anchor = { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height };
      setCamera((current) => zoom(current, event.deltaY < 0 ? 1.15 : 1 / 1.15, content, rect.height / rect.width, anchor));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", onWheel);
    };
    // focusPoint is derived from layout, which is stable for the component's life.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    dragged.current = false;
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    const now = { x: event.clientX, y: event.clientY };
    if (pointers.current.size === 1) {
      const dx = now.x - previous.x;
      const dy = now.y - previous.y;
      if (!dragged.current && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
      if (!dragged.current) event.currentTarget.setPointerCapture(event.pointerId);
      dragged.current = true;
      setCamera((current) => pan(current, dx, dy, size.width));
    } else if (pointers.current.size === 2) {
      const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
      if (other) {
        const before = Math.hypot(previous.x - other.x, previous.y - other.y);
        const after = Math.hypot(now.x - other.x, now.y - other.y);
        const rect = event.currentTarget.getBoundingClientRect();
        const anchor = { x: ((now.x + other.x) / 2 - rect.left) / rect.width, y: ((now.y + other.y) / 2 - rect.top) / rect.height };
        if (before > 0) setCamera((current) => zoom(current, after / before, content, aspect, anchor));
        dragged.current = true;
      }
    }
    pointers.current.set(event.pointerId, now);
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    pointers.current.delete(event.pointerId);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [KEY_PAN_PX, 0],
      ArrowRight: [-KEY_PAN_PX, 0],
      ArrowUp: [0, KEY_PAN_PX],
      ArrowDown: [0, -KEY_PAN_PX],
    };
    const move = moves[event.key];
    if (move) setCamera((current) => pan(current, move[0], move[1], size.width));
    else if (event.key === "+" || event.key === "=") setCamera((current) => zoom(current, 1.25, content, aspect));
    else if (event.key === "-" || event.key === "_") setCamera((current) => zoom(current, 1 / 1.25, content, aspect));
    else if (event.key === "0") setCamera(initialCamera(focusPoint, content, size.width));
    else return;
    event.preventDefault();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="fh-button fh-button-secondary" onClick={() => setCamera((c) => zoom(c, 1.25, content, aspect))}>
          <span aria-hidden="true">+</span> {t("zoomIn")}
        </button>
        <button type="button" className="fh-button fh-button-secondary" onClick={() => setCamera((c) => zoom(c, 1 / 1.25, content, aspect))}>
          <span aria-hidden="true">−</span> {t("zoomOut")}
        </button>
        <button type="button" className="fh-button fh-button-secondary" onClick={() => setCamera(initialCamera(focusPoint, content, size.width))}>
          {t("reset")}
        </button>
      </div>
      <p className="text-sm text-muted">{t("panHint")}</p>
      <div
        ref={frame}
        role="group"
        aria-label={label}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onClickCapture={(event) => {
          // A drag that ends over a card must not open it.
          if (dragged.current) {
            event.preventDefault();
            event.stopPropagation();
            dragged.current = false;
          }
        }}
        className="fh-tree h-[65vh] min-h-80 w-full cursor-grab touch-none overflow-hidden rounded-xl border border-line bg-surface select-none"
      >
        <svg viewBox={viewBox(camera, aspect)} className="size-full" preserveAspectRatio="xMidYMid meet">
          <g className="fh-tree-edges" fill="none">
            {layout.edges.map((edge, index) => {
              const d = edgePath(edge, nodes);
              if (!d) return null;
              const dash = edge.kind === "parent" ? PEDIGREE_DASH[edge.pedigree] : edge.status === "separated" || edge.status === "divorced" ? "6 6" : undefined;
              return <path key={index} d={d} strokeDasharray={dash} className={edge.kind === "union" ? "fh-tree-union" : "fh-tree-link"} />;
            })}
          </g>
          {layout.nodes.map((node) => (
            <Card key={node.key} node={node} person={people[node.personId]} href={`${href.prefix}${encodeURIComponent(node.personId)}${href.suffix}`} t={t} privateLabel={privacy("privateShort")} />
          ))}
        </svg>
      </div>
    </div>
  );
}

function Card({
  node,
  person,
  href,
  t,
  privateLabel,
}: {
  node: LayoutNode;
  person: TreePerson | undefined;
  href: string;
  t: ReturnType<typeof useTranslations<"family.tree">>;
  privateLabel: string;
}) {
  const { x, y } = nodeOrigin(node);
  const name = person?.name ?? "—";
  const dates = [person?.birth ? t("born", { date: person.birth }) : null, person?.death ? t("died", { date: person.death }) : null]
    .filter(Boolean)
    .join(" · ");
  const note = node.repeated
    ? t("repeated")
    : node.hiddenChildren > 0
      ? t("hiddenChildren", { count: node.hiddenChildren })
      : person?.isPrivate
        ? privateLabel
        : "";
  const roleClass = node.role === "focus" ? "fh-tree-focus" : node.role === "partner" ? "fh-tree-partner" : "";
  return (
    <a href={href} aria-label={t("focusOn", { name })} className={`fh-tree-card ${roleClass}`}>
      <title>{[name, dates, note].filter(Boolean).join(" · ")}</title>
      <rect x={x} y={y} width={CARD_WIDTH} height={CARD_HEIGHT} rx={10} />
      <text x={x + 10} y={y + 24} className="fh-tree-name">
        {fitName(name)}
      </text>
      <text x={x + 10} y={y + 44} className="fh-tree-meta">
        {fitName(dates, 26)}
      </text>
      <text x={x + 10} y={y + 62} className="fh-tree-note">
        {fitName(note, 26)}
      </text>
    </a>
  );
}
