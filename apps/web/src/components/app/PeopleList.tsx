import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import type { PersonSummary } from "@/lib/api/schemas";

export async function PeopleList({ locale, people }: { locale: Locale; people: readonly PersonSummary[] }) {
  if (people.length === 0) return null;
  const t = await getTranslations({ locale, namespace: "app.space" });
  const person = await getTranslations({ locale, namespace: "app.person" });
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
      {people.map((entry) => (
        <li key={entry.id}>
          <a
            href={`/${locale}/personas/${encodeURIComponent(entry.id)}`}
            className="flex flex-col gap-1 p-4 text-fg no-underline hover:bg-amate"
          >
            <span className="font-serif text-lg font-bold text-accent">{entry.display_name}</span>
            <span className="flex flex-wrap gap-x-4 text-sm text-muted">
              <span>{person(`living.${entry.living_status}`)}</span>
              {entry.birth?.date_value ? (
                <span>{t.rich("born", { date: entry.birth.date_value, mono: (chunks) => <span className="fh-date">{chunks}</span> })}</span>
              ) : null}
              {entry.death?.date_value ? (
                <span>{t.rich("died", { date: entry.death.date_value, mono: (chunks) => <span className="fh-date">{chunks}</span> })}</span>
              ) : null}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
