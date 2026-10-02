import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AddPersonForm } from "@/components/app/AddPersonForm";
import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { PeopleList } from "@/components/app/PeopleList";
import { isLocale } from "@/i18n/locales";
import { listPeople, listSpaces } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { errorCopy } from "@/lib/i18n/error-copy";

type Params = Promise<{ locale: string; spaceId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "app.space" });
  return { title: t("peopleTitle") };
}

function single(value: string | string[] | undefined): string | undefined {
  const text = typeof value === "string" ? value.trim() : undefined;
  return text ? text.slice(0, 120) : undefined;
}

/** A family space: people with search and paging, «Agregar persona», and the tree placeholder. */
export default async function SpacePage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, spaceId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const query = await searchParams;
  const q = single(query.q);
  const cursor = single(query.cursor);
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "app.space" });
  const form = await getTranslations({ locale, namespace: "app.personForm" });
  const common = await getTranslations({ locale, namespace: "common" });
  const here = `/${locale}/familias/${encodeURIComponent(spaceId)}`;

  const [spaces, people] = await Promise.all([
    load(() => listSpaces(api)),
    load(() => listPeople(api, spaceId, { q, cursor })),
  ]);
  if (!people.ok && people.code === "not_found") notFound();
  if (!people.ok) return <ApiErrorNotice locale={locale} code={people.code} returnTo={here} />;
  const space = spaces.ok ? spaces.data.find((candidate) => candidate.id === spaceId) : undefined;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <a href={`/${locale}`} className="text-sm">
          ← {t("breadcrumb")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{space?.name ?? t("peopleTitle")}</h1>
      </div>

      <section aria-labelledby="personas" className="flex flex-col gap-4">
        <h2 id="personas" className="text-2xl font-bold">
          {t("peopleTitle")}
        </h2>
        <form method="get" action={here} role="search" className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex grow flex-col gap-1">
            <label htmlFor="buscar" className="font-semibold">
              {t("searchLabel")}
            </label>
            <input id="buscar" name="q" type="search" defaultValue={q ?? ""} maxLength={120} className="fh-input" />
          </div>
          <button type="submit" className="fh-button">
            {t("searchButton")}
          </button>
          {q ? (
            <a href={here} className="fh-button fh-button-secondary">
              {t("clearSearch")}
            </a>
          ) : null}
        </form>
        <PeopleList locale={locale} people={people.data.items} />
        {people.data.items.length === 0 ? (
          <p className="rounded-xl bg-amate p-5 text-bark">{q ? t("noResults", { query: q }) : t("empty")}</p>
        ) : null}
        {people.data.next_cursor ? (
          <p>
            <a
              href={`${here}?${new URLSearchParams({ ...(q ? { q } : {}), cursor: people.data.next_cursor }).toString()}`}
              className="fh-button fh-button-secondary"
            >
              {t("more")}
            </a>
          </p>
        ) : null}
      </section>

      <div className="max-w-2xl">
        <AddPersonForm
          locale={locale}
          spaceId={spaceId}
          copy={{
            title: form("title"),
            lead: form("lead"),
            given: form("given"),
            paternal: form("paternal"),
            maternal: form("maternal"),
            nickname: form("nickname"),
            nicknameHint: form("nicknameHint"),
            sex: form("sex"),
            sexOptions: {
              M: form("sexOptions.M"),
              F: form("sexOptions.F"),
              X: form("sexOptions.X"),
              U: form("sexOptions.U"),
            },
            birthDate: form("birthDate"),
            birthDateHint: form("birthDateHint"),
            submit: form("submit"),
            submitting: form("submitting"),
            invalid: { nameRequired: form("errors.nameRequired"), tooLong: form("errors.tooLong") },
            failed: await errorCopy(locale),
          }}
        />
      </div>

      <section aria-labelledby="arbol" className="rounded-xl border-2 border-dashed border-line-strong p-6">
        <p className="inline-flex rounded-full bg-amate px-3 py-1 text-sm font-semibold text-bark">
          {common("comingSoon")}
        </p>
        <h2 id="arbol" className="mt-3 text-2xl font-bold">
          {t("treeTitle")}
        </h2>
        <p className="mt-2 text-muted">{t("treeBody")}</p>
      </section>
    </div>
  );
}
