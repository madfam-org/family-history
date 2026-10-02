import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { isPrivatePerson, type PersonSummary } from "@/lib/api/schemas";
import { displayDate } from "@/lib/dates/hints";

export async function PeopleList({ locale, people }: { locale: Locale; people: readonly PersonSummary[] }) {
  if (people.length === 0) return null;
  const t = await getTranslations({ locale, namespace: "app.space" });
  const person = await getTranslations({ locale, namespace: "app.person" });
  const privacy = await getTranslations({ locale, namespace: "family.privacy" });
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
      {people.map((entry) => {
        const born = entry.birth ? displayDate(entry.birth, locale) : null;
        const died = entry.death ? displayDate(entry.death, locale) : null;
        return (
        <li key={entry.id}>
          <a
            href={`/${locale}/personas/${encodeURIComponent(entry.id)}`}
            className="flex flex-col gap-1 p-4 text-fg no-underline hover:bg-amate"
          >
            <span className="font-serif text-lg font-bold text-accent">{entry.display_name}</span>
            <span className="flex flex-wrap gap-x-4 text-sm text-muted">
              <span>{person(`living.${entry.living_status}`)}</span>
              {isPrivatePerson(entry) ? <span className="font-semibold text-bark">{privacy("privateShort")}</span> : null}
              {born ? <span>{t.rich("born", { date: born, mono: (chunks) => <span className="fh-date">{chunks}</span> })}</span> : null}
              {died ? <span>{t.rich("died", { date: died, mono: (chunks) => <span className="fh-date">{chunks}</span> })}</span> : null}
            </span>
          </a>
        </li>
        );
      })}
    </ul>
  );
}
