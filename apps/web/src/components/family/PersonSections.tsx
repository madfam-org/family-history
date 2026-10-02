import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { removeRelationshipAction } from "@/app/actions/relatives";
import type { Locale } from "@/i18n/locales";
import type { Person, Sex } from "@/lib/api/schemas";
import { displayDate } from "@/lib/dates/hints";
import { takesGodparents } from "@/lib/forms/family";
import { eventTypeKey, formatName } from "@/lib/people/labels";
import { asPartnerStatus, asPedigree } from "@/lib/tree/graph";

import { ConfirmRemove } from "./ConfirmRemove";
import { GodparentsEditor, type GodparentEntry } from "./GodparentsEditor";
import { SensitiveMarker } from "./PrivacyBadges";

export interface KnownPerson {
  name: string;
  sex: Sex;
}

export function Section({ id, title, empty, children }: { id: string; title: string; empty: string; children: ReactNode[] }) {
  return (
    <section aria-labelledby={id} className="fh-card">
      <h2 id={id} className="text-xl font-bold">
        {title}
      </h2>
      {children.length > 0 ? <ul className="mt-3 flex flex-col gap-4">{children}</ul> : <p className="mt-3 text-muted">{empty}</p>}
    </section>
  );
}

export async function NamesSection({ locale, person }: { locale: Locale; person: Person }) {
  const t = await getTranslations({ locale, namespace: "app.person" });
  return (
    <Section id="nombres" title={t("namesTitle")} empty={t("noNames")}>
      {person.names.map((name, index) => {
        const nicknames = name.nicknames.filter(Boolean);
        return (
          <li key={name.id ?? index}>
            <p className="font-serif text-lg font-bold">{formatName(name) || person.display_name}</p>
            {name.nombre_usado ? <p className="text-sm text-muted">{name.nombre_usado}</p> : null}
            {nicknames.length > 0 ? <p className="text-sm text-muted">{t("nickname", { nickname: nicknames.join(", ") })}</p> : null}
          </li>
        );
      })}
    </Section>
  );
}

/** Events with humanized dates, sensitive markers and, on sacraments, their padrinos. */
export async function EventsSection({
  locale,
  person,
  known,
}: {
  locale: Locale;
  person: Person;
  known: ReadonlyMap<string, KnownPerson>;
}) {
  const t = await getTranslations({ locale, namespace: "family" });
  const personCopy = await getTranslations({ locale, namespace: "app.person" });
  return (
    <Section id="eventos" title={t("events.title")} empty={personCopy("noEvents")}>
      {person.events.map((event, index) => {
        const key = eventTypeKey(event.type);
        const date = displayDate(event, locale);
        const entries: GodparentEntry[] = event.associations.map((association) => {
          const who = known.get(association.person_id);
          return {
            id: association.id,
            personId: association.person_id,
            name: association.display_name ?? who?.name ?? t("relationships.unknownPerson"),
            sex: who?.sex ?? "U",
            role: association.role,
            phrase: association.phrase ?? null,
          };
        });
        return (
          <li key={event.id ?? index}>
            <p className="font-semibold">{key === "other" ? event.type : t(`events.types.${key}`)}</p>
            <p className="text-sm text-muted">
              <span className="fh-date">{date ?? t("dates.unknown")}</span>
              {event.place ? ` · ${event.place}` : null}
            </p>
            <SensitiveMarker locale={locale} sensitivity={event.sensitivity} />
            {event.id && person.space_id && takesGodparents(event.type) ? (
              <GodparentsEditor spaceId={person.space_id} eventId={event.id} principalId={person.id} entries={entries} />
            ) : null}
          </li>
        );
      })}
    </Section>
  );
}

/** Parents, children and partners by name, with pedigree or status, each removable. */
export async function RelativesSection({
  locale,
  person,
  known,
}: {
  locale: Locale;
  person: Person;
  known: ReadonlyMap<string, KnownPerson>;
}) {
  const t = await getTranslations({ locale, namespace: "family.relationships" });
  return (
    <Section id="relaciones" title={t("title")} empty={t("empty")}>
      {person.relationships.map((relationship) => {
        const otherId = relationship.from_person_id === person.id ? relationship.to_person_id : relationship.from_person_id;
        const other = known.get(otherId);
        const name = other?.name ?? t("unknownPerson");
        const sex = other?.sex ?? "U";
        let label: string;
        if (relationship.type === "union") {
          label = `${t("labels.partner")} · ${t(`statuses.${asPartnerStatus(relationship.qualifier)}`)}`;
        } else {
          const pedigree = asPedigree(relationship.qualifier);
          const base = relationship.to_person_id === person.id ? t(`labels.parent.${sex}`) : t(`labels.child.${sex}`);
          label = pedigree === "birth" ? base : `${base} · ${t(`pedigreeShort.${pedigree}`)}`;
        }
        return (
          <li key={relationship.id} className="flex flex-col gap-2">
            <p>
              <span className="text-sm text-muted">{label}: </span>
              <a href={`/${locale}/personas/${encodeURIComponent(otherId)}`} className="font-semibold">
                {name}
              </a>
            </p>
            <ConfirmRemove
              action={removeRelationshipAction}
              field="relationshipId"
              id={relationship.id}
              label={t("removeLabel", { name })}
              question={t("confirmRemove", { name })}
              done={t("removed")}
            />
          </li>
        );
      })}
    </Section>
  );
}

export async function CitationsSection({ locale, person }: { locale: Locale; person: Person }) {
  const t = await getTranslations({ locale, namespace: "app.person" });
  return (
    <Section id="fuentes" title={t("citationsTitle")} empty={t("noCitations")}>
      {person.citations.map((citation) => (
        <li key={citation.id}>
          <p className="fh-date text-sm">
            {[
              citation.page,
              citation.foja ? t("citationFoja", { value: citation.foja }) : null,
              citation.partida ? t("citationPartida", { value: citation.partida }) : null,
            ]
              .filter(Boolean)
              .join(" · ") || citation.id}
          </p>
        </li>
      ))}
    </Section>
  );
}
