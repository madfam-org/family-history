import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ApiErrorNotice } from "@/components/app/ApiErrorNotice";
import { KinshipForm } from "@/components/family/KinshipForm";
import { isLocale } from "@/i18n/locales";
import { getKinship } from "@/lib/api/endpoints";
import { load } from "@/lib/api/load";
import { requireApi } from "@/lib/auth/server";
import { asId } from "@/lib/forms/family";
import { fetchPeople } from "@/lib/tree/load";

type Params = Promise<{ locale: string; spaceId: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "family.kinship" });
  return { title: t("pageTitle") };
}

/** Pick two people and read what one is to the other («tu tío abuelo», «concuño»…). */
export default async function KinshipPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { locale, spaceId } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const query = await searchParams;
  const egoId = asId(query.de);
  const alterId = asId(query.a);
  const { api } = await requireApi();
  const t = await getTranslations({ locale, namespace: "family.kinship" });
  const personCopy = await getTranslations({ locale, namespace: "app.person" });
  const here = `/${locale}/familias/${encodeURIComponent(spaceId)}/parentesco`;

  const chosen = await fetchPeople(api, [egoId, alterId].filter((id): id is string => id !== null));
  const byId = new Map(chosen.people.map((person) => [person.id, { id: person.id, display_name: person.display_name }]));
  const ego = egoId ? (byId.get(egoId) ?? null) : null;
  const alter = alterId ? (byId.get(alterId) ?? null) : null;

  let answer: { kind: "result"; text: string } | { kind: "notice"; text: string } | null = null;
  if (query.de !== undefined || query.a !== undefined) {
    if (!ego || !alter) answer = { kind: "notice", text: t("pickBoth") };
    else if (ego.id === alter.id) answer = { kind: "notice", text: t("samePerson") };
    else {
      const kinship = await load(() => getKinship(api, ego.id, alter.id));
      if (kinship.ok) {
        const label = locale === "en" ? kinship.data.label_en : kinship.data.label_es;
        answer = { kind: "result", text: t("result", { alter: alter.display_name, label, ego: ego.display_name }) };
      } else if (kinship.code === "no_relation") {
        answer = { kind: "notice", text: t("noRelation") };
      } else if (kinship.code === "not_found") {
        // 404 person_not_found: `to` is not someone the caller can see in this space.
        answer = { kind: "notice", text: t("personMissing") };
      } else {
        return <ApiErrorNotice locale={locale} code={kinship.code} returnTo={here} />;
      }
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <a href={`/${locale}/familias/${encodeURIComponent(spaceId)}`} className="text-sm">
          ← {personCopy("breadcrumb")}
        </a>
        <h1 className="mt-2 text-3xl font-bold">{t("title")}</h1>
        <p className="mt-2 text-muted">{t("lead")}</p>
      </div>
      {answer ? (
        <div role="status" className={answer.kind === "result" ? "rounded-xl bg-amate p-5 text-bark" : "rounded-xl border-2 border-line-strong p-5"}>
          <p className={answer.kind === "result" ? "font-serif text-2xl font-bold" : ""}>{answer.text}</p>
          {answer.kind === "result" && ego && alter ? (
            <p className="mt-3">
              <a href={`${here}?${new URLSearchParams({ de: alter.id, a: ego.id }).toString()}`}>{t("swap")}</a>
            </p>
          ) : null}
        </div>
      ) : null}
      <KinshipForm action={here} spaceId={spaceId} ego={ego} alter={alter} />
    </div>
  );
}
