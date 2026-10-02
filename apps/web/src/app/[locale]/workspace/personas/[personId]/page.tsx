import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { isLocale } from "@/i18n/locales";
import { getPerson } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { eventTypeKey, formatName, relationshipTypeKey } from "@/lib/people/labels";

type Params = Promise<{ locale: string; personId: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.person" });
  return { title: t("namesTitle") };
}

function Section({ id, title, empty, children }: { id: string; title: string; empty: string; children: ReactNode[] }) {
  return (
    <section aria-labelledby={id} className="fh-card">
      <h2 id={id} className="text-xl font-bold">
        {title}
      </h2>
      {children.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-3">{children}</ul>
      ) : (
        <p className="mt-3 text-muted">{empty}</p>
      )}
    </section>
  );
}

/** A person: names, events, relationships and cited sources, with honest empty states. */
export default async function PersonPage({ params }: { params: Params }) {
  const { locale, personId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "app.person" });
  const form = await getTranslations({ locale, namespace: "app.personForm" });
  const here = `/${locale}/personas/${encodeURIComponent(personId)}`;

  const result = await load(() => getPerson(api, personId));
  if (!result.ok && result.code === "not_found") notFound();
  if (!result.ok) return <ApiErrorNotice locale={locale} code={result.code} returnTo={here} />;
  const person = result.data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        {person.space_id ? (
          <a href={`/${locale}/familias/${encodeURIComponent(person.space_id)}`} className="text-sm">
            ← {t("breadcrumb")}
          </a>
        ) : null}
        <h1 className="mt-2 text-3xl font-bold">{person.display_name}</h1>
        <p className="mt-2 flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">
            {t(`living.${person.living_status}`)}
          </span>
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">
            {t(`visibility.${person.visibility}`)}
          </span>
          <span className="rounded-full bg-amate px-3 py-1 font-semibold text-bark">
            {t("sex", { sex: form(`sexOptions.${person.sex}`) })}
          </span>
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section id="nombres" title={t("namesTitle")} empty={t("noNames")}>
          {person.names.map((name, index) => {
            const nicknames = [name.nickname, ...(name.nicknames ?? [])].filter(Boolean);
            return (
              <li key={name.id ?? index}>
                <p className="font-serif text-lg font-bold">{formatName(name) || person.display_name}</p>
                {nicknames.length > 0 ? (
                  <p className="text-sm text-muted">{t("nickname", { nickname: nicknames.join(", ") })}</p>
                ) : null}
              </li>
            );
          })}
        </Section>

        <Section id="eventos" title={t("eventsTitle")} empty={t("noEvents")}>
          {person.events.map((event, index) => {
            const key = eventTypeKey(event.type);
            const date = event.date_value ?? event.date_original;
            return (
              <li key={event.id ?? index}>
                <p className="font-semibold">{key === "other" ? event.type : t(`eventTypes.${key}`)}</p>
                <p className="text-sm text-muted">
                  <span className="fh-date">{date ?? t("unknownDate")}</span>
                  {event.place ? ` · ${event.place}` : null}
                </p>
              </li>
            );
          })}
        </Section>

        <Section id="relaciones" title={t("relationshipsTitle")} empty={t("noRelationships")}>
          {person.relationships.map((relationship) => {
            const key = relationshipTypeKey(relationship.type);
            const otherId =
              relationship.from_person_id === person.id ? relationship.to_person_id : relationship.from_person_id;
            return (
              <li key={relationship.id}>
                <p className="font-semibold">
                  {key === "other" ? relationship.type : t(`relationshipTypes.${key}`)}
                  {relationship.qualifier ? <span className="font-normal text-muted"> · {relationship.qualifier}</span> : null}
                </p>
                <a href={`/${locale}/personas/${encodeURIComponent(otherId)}`} className="text-sm">
                  {t("relatedPerson")}
                </a>
              </li>
            );
          })}
        </Section>

        <Section id="fuentes" title={t("citationsTitle")} empty={t("noCitations")}>
          {person.citations.map((citation) => (
            <li key={citation.id}>
              <p className="font-semibold">{citation.title ?? citation.id}</p>
              {citation.detail ? <p className="fh-date text-sm text-muted">{citation.detail}</p> : null}
            </li>
          ))}
        </Section>
      </div>
    </div>
  );
}
