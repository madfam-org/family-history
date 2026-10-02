import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { TreeCanvas } from "@/components/tree/TreeCanvas";
import { TreeLegend, TreeOutline } from "@/components/tree/TreeOutline";
import { isLocale } from "@/i18n/locales";
import { getPerson } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { buildGraph } from "@/lib/tree/graph";
import { layoutAncestors, layoutDescendants } from "@/lib/tree/layout";
import { loadNeighbourhood } from "@/lib/tree/load";

type Params = Promise<{ locale: string; personId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

const UP = 4;
const DOWN = 3;
const MAX_PEOPLE = 80;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "family.tree" });
  return { title: t("pageTitle") };
}

/** The family tree around one person: ancestors (pedigree) or descendants, drawn and listed. */
export default async function TreePage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, personId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const mode = (await searchParams).vista === "descendientes" ? "descendants" : "ancestors";
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "family" });
  const personPath = `/${locale}/personas/${encodeURIComponent(personId)}`;
  const here = `${personPath}/arbol${mode === "descendants" ? "?vista=descendientes" : ""}`;

  const focus = await load(() => getPerson(api, personId));
  if (!focus.ok && focus.code === "not_found") notFound();
  if (!focus.ok) return <ApiErrorNotice locale={locale} code={focus.code} returnTo={here} />;

  const around = await load(() =>
    loadNeighbourhood(api, focus.data, {
      up: mode === "ancestors" ? UP : 0,
      down: mode === "descendants" ? DOWN : 0,
      maxPeople: MAX_PEOPLE,
    }),
  );
  if (!around.ok) return <ApiErrorNotice locale={locale} code={around.code} returnTo={here} />;

  const graph = buildGraph(around.data.people, locale);
  const layout = mode === "ancestors" ? layoutAncestors(graph, personId, UP) : layoutDescendants(graph, personId, DOWN);
  const people = Object.fromEntries(graph.people);
  const href = {
    prefix: `/${locale}/personas/`,
    suffix: `/arbol${mode === "descendants" ? "?vista=descendientes" : ""}`,
  };
  const name = focus.data.display_name;
  const empty = layout.nodes.length <= 1;
  const tab = (target: "ancestors" | "descendants") =>
    `fh-button ${mode === target ? "" : "fh-button-secondary"}`;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <a href={personPath} className="text-sm">
          ← {t("nav.backToPerson")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{t("tree.title", { name })}</h1>
      </div>

      <nav aria-label={t("tree.viewLabel")} className="flex flex-wrap gap-2">
        <a href={`${personPath}/arbol`} className={tab("ancestors")} aria-current={mode === "ancestors" ? "page" : undefined}>
          {t("tree.ancestors")}
        </a>
        <a
          href={`${personPath}/arbol?vista=descendientes`}
          className={tab("descendants")}
          aria-current={mode === "descendants" ? "page" : undefined}
        >
          {t("tree.descendants")}
        </a>
      </nav>

      {around.data.truncated ? (
        <p role="status" className="rounded-xl bg-amate p-4 text-bark">
          {t("tree.truncated", { max: MAX_PEOPLE })}
        </p>
      ) : null}
      {around.data.failed > 0 ? (
        <p role="alert" className="rounded-xl border-2 border-danger p-4 font-semibold text-danger">
          {t("tree.failed", { count: around.data.failed })}
        </p>
      ) : null}

      {empty ? (
        <p className="rounded-xl bg-amate p-5 text-bark">
          {mode === "ancestors" ? t("tree.emptyAncestors") : t("tree.emptyDescendants")}
        </p>
      ) : (
        <>
          <TreeLegend locale={locale} />
          <TreeCanvas
            layout={layout}
            people={people}
            href={href}
            label={t("tree.drawingLabel", { name, count: new Set(layout.nodes.map((node) => node.personId)).size })}
          />
        </>
      )}

      <TreeOutline locale={locale} outline={layout.outline} people={people} href={href} />
    </div>
  );
}
