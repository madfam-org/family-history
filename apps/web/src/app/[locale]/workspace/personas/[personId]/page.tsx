import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { AddRelativeForm } from "@/components/family/AddRelativeForm";
import { CompadrazgoPanel } from "@/components/family/CompadrazgoPanel";
import {
  CitationsSection,
  EventsSection,
  NamesSection,
  RelativesSection,
  type KnownPerson,
} from "@/components/family/PersonSections";
import { PrivatePersonBadge } from "@/components/family/PrivacyBadges";
import { isLocale } from "@/i18n/locales";
import { getCompadrazgo, getPerson } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { isPrivatePerson } from "@/lib/api/schemas";
import { requireApi } from "@/lib/auth/server";
import { fetchPeople, relatedIds } from "@/lib/tree/load";

type Params = Promise<{ locale: string; personId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.person" });
  return { title: t("pageTitle") };
}

/**
 * A person: names, events (with padrinos on sacraments), relatives with the relationship editor,
 * compadrazgo and cited sources. Privacy is shown, not implied.
 */
export default async function PersonPage({ params }: { params: Params }) {
  const { locale, personId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "app.person" });
  const family = await getTranslations({ locale, namespace: "family" });
  const form = await getTranslations({ locale, namespace: "app.personForm" });
  const here = `/${locale}/personas/${encodeURIComponent(personId)}`;

  const result = await load(() => getPerson(api, personId));
  if (!result.ok && result.code === "not_found") notFound();
  if (!result.ok) return <ApiErrorNotice locale={locale} code={result.code} returnTo={here} />;
  const person = result.data;

  // Names (and sex, for padrino/madrina) of everyone this page mentions.
  const associated = person.events.flatMap((event) => event.associations.map((association) => association.person_id));
  const ids = [...new Set([...relatedIds(person), ...associated])].filter((id) => id !== person.id);
  const [related, compadrazgo] = await Promise.all([
    fetchPeople(api, ids),
    load(() => getCompadrazgo(api, person.id)),
  ]);
  const known = new Map<string, KnownPerson>(related.people.map((other) => [other.id, { name: other.display_name, sex: other.sex }]));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        {person.space_id ? (
          <a href={`/${locale}/familias/${encodeURIComponent(person.space_id)}`} className="text-sm">
            ← {t("breadcrumb")}
          </a>
        ) : null}
        <h1 className="text-3xl font-bold">{person.display_name}</h1>
        <p className="flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">{t(`living.${person.living_status}`)}</span>
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">{t(`visibility.${person.visibility}`)}</span>
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">
            {t("sex", { sex: form(`sexOptions.${person.sex}`) })}
          </span>
        </p>
        {isPrivatePerson(person) ? <PrivatePersonBadge locale={locale} /> : null}
        <nav aria-label={family("nav.toolsTitle")} className="flex flex-wrap gap-2">
          <a href={`${here}/editar`} className="fh-button">
            {family("nav.editPerson")}
          </a>
          <a href={`${here}/arbol`} className="fh-button fh-button-secondary">
            {family("nav.tree")}
          </a>
          {person.space_id ? (
            <a
              href={`/${locale}/familias/${encodeURIComponent(person.space_id)}/parentesco?${new URLSearchParams({ de: person.id }).toString()}`}
              className="fh-button fh-button-secondary"
            >
              {family("nav.kinship")}
            </a>
          ) : null}
        </nav>
      </div>

      {related.failed > 0 ? (
        <p role="alert" className="rounded-xl border-2 border-danger p-4 font-semibold text-danger">
          {family("tree.failed", { count: related.failed })}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <NamesSection locale={locale} person={person} />
        <EventsSection locale={locale} person={person} known={known} />
        <RelativesSection locale={locale} person={person} known={known} />
        <CompadrazgoPanel
          locale={locale}
          result={compadrazgo.ok ? { ok: true, items: compadrazgo.data.items } : { ok: false, code: compadrazgo.code }}
        />
        <CitationsSection locale={locale} person={person} />
      </div>

      {person.space_id ? (
        <div className="max-w-2xl">
          <AddRelativeForm
            personId={person.id}
            spaceId={person.space_id}
            nameLabels={{ given: form("given"), paternal: form("paternal"), maternal: form("maternal") }}
          />
        </div>
      ) : null}
    </div>
  );
}
