import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { AddEventForm, CorrectDateForm } from "@/components/family/EventForms";
import { NameEditorForm } from "@/components/family/NameEditorForm";
import { SensitiveMarker } from "@/components/family/PrivacyBadges";
import { isLocale } from "@/i18n/locales";
import { getPerson } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { displayDate } from "@/lib/dates/hints";
import { nameValuesFrom, primaryName } from "@/lib/forms/names";
import { eventTypeKey } from "@/lib/people/labels";
import { fetchPeople, partnerIds } from "@/lib/tree/load";

type Params = Promise<{ locale: string; personId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "family.editor" });
  return { title: t("pageTitle") };
}

/** «Editar persona»: the Mexican name model and the person's events with free-text dates. */
export default async function EditPersonPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, personId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const refusal = (await searchParams).fecha;
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "family" });
  const form = await getTranslations({ locale, namespace: "app.personForm" });
  const errors = await getTranslations({ locale, namespace: "errors" });
  const personCopy = await getTranslations({ locale, namespace: "app.person" });
  const personPath = `/${locale}/personas/${encodeURIComponent(personId)}`;

  const result = await load(() => getPerson(api, personId));
  if (!result.ok && result.code === "not_found") notFound();
  if (!result.ok) return <ApiErrorNotice locale={locale} code={result.code} returnTo={`${personPath}/editar`} />;
  const person = result.data;
  const partners = await fetchPeople(api, partnerIds(person));
  const refusalHint =
    refusal === "ambiguous_date"
      ? t("dates.hints.ambiguous")
      : refusal === "invalid_date"
        ? t("dates.hints.invalid")
        : refusal
          ? errors("unknown")
          : null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <a href={personPath} className="text-sm">
          ← {t("nav.backToPerson")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{t("editor.title", { name: person.display_name })}</h1>
      </div>

      {refusalHint ? (
        <p role="alert" className="rounded-xl border-2 border-danger p-4">
          {t("events.birthNotSaved", { hint: refusalHint })}
        </p>
      ) : null}

      <div className="max-w-2xl">
        <NameEditorForm
          personId={person.id}
          initial={nameValuesFrom(primaryName(person.names), person.sex)}
          sexLabels={{ M: form("sexOptions.M"), F: form("sexOptions.F"), X: form("sexOptions.X"), U: form("sexOptions.U") }}
        />
      </div>

      <section aria-labelledby="eventos" className="fh-card max-w-2xl">
        <h2 id="eventos" className="text-xl font-bold">
          {t("events.title")}
        </h2>
        {person.events.length === 0 ? (
          <p className="mt-3 text-muted">{personCopy("noEvents")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-4">
            {person.events.map((event, index) => {
              const key = eventTypeKey(event.type);
              const date = displayDate(event, locale);
              return (
                <li key={event.id ?? index}>
                  <p className="font-semibold">{key === "other" ? event.type : t(`events.types.${key}`)}</p>
                  <p className="text-sm text-muted">
                    <span className="fh-date">{date ?? t("dates.unknown")}</span>
                    {event.date_original && date !== event.date_original ? (
                      <span className="ml-2">{t("dates.asWritten", { text: event.date_original })}</span>
                    ) : null}
                  </p>
                  <SensitiveMarker locale={locale} sensitivity={event.sensitivity} />
                  {event.id ? <CorrectDateForm eventId={event.id} current={event.date_original ?? ""} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="max-w-2xl">
        <AddEventForm
          personId={person.id}
          spaceId={person.space_id ?? ""}
          partners={partners.people.map((partner) => ({ id: partner.id, name: partner.display_name }))}
        />
      </div>
    </div>
  );
}
