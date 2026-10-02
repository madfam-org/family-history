import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import type { TreePerson } from "@/lib/tree/graph";
import type { OutlineItem } from "@/lib/tree/layout";
import { PEDIGREE_DASH } from "@/lib/tree/geometry";

type T = Awaited<ReturnType<typeof getTranslations<"family">>>;

function relationLabel(item: OutlineItem, person: TreePerson | undefined, t: T): string | null {
  const link = item.link;
  if (!link) return null;
  const sex = person?.sex ?? "U";
  if (link.kind === "partner") return `${t("relationships.labels.partner")} · ${t(`relationships.statuses.${link.status}`)}`;
  const base = link.kind === "parent" ? t(`relationships.labels.parent.${sex}`) : t(`relationships.labels.child.${sex}`);
  return link.pedigree === "birth" ? base : `${base} · ${t(`relationships.pedigreeShort.${link.pedigree}`)}`;
}

function Item({ item, people, t, href }: {
  item: OutlineItem;
  people: Readonly<Record<string, TreePerson>>;
  t: T;
  href: { prefix: string; suffix: string };
}) {
  const person = people[item.personId];
  const name = person?.name ?? t("relationships.unknownPerson");
  const relation = relationLabel(item, person, t);
  const dates = [person?.birth ? t("tree.born", { date: person.birth }) : null, person?.death ? t("tree.died", { date: person.death }) : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="mt-2">
      <p>
        {relation ? <span className="text-sm text-muted">{relation}: </span> : null}
        <a href={`${href.prefix}${encodeURIComponent(item.personId)}${href.suffix}`} className="font-semibold">
          {name}
        </a>
        {dates ? <span className="fh-date ml-2 text-muted">{dates}</span> : null}
        {person?.isPrivate ? <span className="ml-2 text-sm text-bark">({t("privacy.privateShort")})</span> : null}
        {item.repeated ? <span className="ml-2 text-sm text-muted">({t("tree.repeated")})</span> : null}
      </p>
      {item.children.length > 0 ? (
        <ul className="ml-4 border-l border-line pl-3">
          {item.children.map((child, index) => (
            <Item key={`${child.personId}-${index}`} item={child} people={people} t={t} href={href} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** The tree as nested lists: the accessible alternative to the drawing, always rendered. */
export async function TreeOutline({
  locale,
  outline,
  people,
  href,
}: {
  locale: Locale;
  outline: OutlineItem;
  people: Readonly<Record<string, TreePerson>>;
  href: { prefix: string; suffix: string };
}) {
  const t = await getTranslations({ locale, namespace: "family" });
  return (
    <section aria-labelledby="arbol-lista" className="fh-card">
      <h2 id="arbol-lista" className="text-xl font-bold">
        {t("tree.listTitle")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("tree.listLead")}</p>
      <ul className="mt-2">
        <Item item={outline} people={people} t={t} href={href} />
      </ul>
    </section>
  );
}

/** What each line pattern means. Decorative samples; the words carry the meaning. */
export async function TreeLegend({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "family.tree" });
  const rows = [
    { label: t("legendBirth"), dash: PEDIGREE_DASH.birth, union: false },
    { label: t("legendAdopted"), dash: PEDIGREE_DASH.adopted, union: false },
    { label: t("legendFoster"), dash: PEDIGREE_DASH.foster, union: false },
    { label: t("legendStep"), dash: PEDIGREE_DASH.step, union: false },
    { label: t("legendUnion"), dash: undefined, union: true },
  ];
  return (
    <div>
      <h2 className="text-base font-semibold">{t("legendTitle")}</h2>
      <ul className="fh-tree-legend mt-1 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {rows.map((row) => (
          <li key={row.label} className="inline-flex items-center gap-2">
            <svg aria-hidden="true" viewBox="0 0 40 8" className="h-2 w-10">
              <line x1="0" y1="4" x2="40" y2="4" strokeDasharray={row.dash} className={row.union ? "fh-tree-legend-union" : undefined} />
            </svg>
            {row.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
