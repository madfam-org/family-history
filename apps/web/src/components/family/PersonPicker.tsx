"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useId, useState, useTransition } from "react";

import { searchPeopleAction, type PeopleSearchResult } from "@/app/actions/relatives";
import type { ErrorCode } from "@/lib/api/errors";
import { displayDate } from "@/lib/dates/hints";

export interface PickedPerson {
  id: string;
  display_name: string;
}

type SearchFn = (spaceId: string, query: string) => Promise<PeopleSearchResult>;

const DEBOUNCE_MS = 300;

/**
 * Picks a person of the family space by name. Results are radio buttons (one tab stop, arrow
 * keys to move), the count is announced politely, and the choice is posted as a hidden field.
 * The search itself is the API's: accent- and nickname-insensitive.
 */
export function PersonPicker({
  spaceId,
  name,
  label,
  excludeId,
  initial,
  search = searchPeopleAction,
  onPick,
}: {
  spaceId: string;
  name: string;
  label?: string;
  excludeId?: string;
  initial?: PickedPerson | null;
  search?: SearchFn;
  onPick?: (person: PickedPerson | null) => void;
}) {
  const t = useTranslations("family.picker");
  const errors = useTranslations("errors");
  const locale = useLocale() === "en" ? "en" : "es";
  const inputId = useId();
  const hintId = useId();
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<PickedPerson | null>(initial ?? null);
  const [result, setResult] = useState<PeopleSearchResult | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    const timer = setTimeout(() => {
      startTransition(async () => {
        try {
          setResult(await search(spaceId, q));
        } catch {
          setResult({ ok: false, code: "api_unreachable" });
        }
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, search, spaceId]);

  function choose(person: PickedPerson | null) {
    setPicked(person);
    onPick?.(person);
  }

  if (picked) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3">
        <input type="hidden" name={name} value={picked.id} />
        <p role="status" className="grow">
          {t("chosen", { name: picked.display_name })}
        </p>
        <button type="button" className="fh-button fh-button-secondary" onClick={() => choose(null)}>
          {t("change")}
        </button>
      </div>
    );
  }

  const items = result?.ok ? result.items.filter((item) => item.id !== excludeId) : [];
  const short = query.trim().length < 2;
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="font-semibold">
        {label ?? t("label")}
      </label>
      <input
        id={inputId}
        type="search"
        value={query}
        maxLength={120}
        autoComplete="off"
        aria-describedby={hintId}
        onChange={(event) => setQuery(event.target.value)}
        className="fh-input"
      />
      <p id={hintId} className="text-sm text-muted">
        {t("hint")}
      </p>
      <p role="status" aria-live="polite" className="text-sm">
        {short ? "" : pending ? t("searching") : resultMessage(result, items.length, t, errors)}
      </p>
      {!short && items.length > 0 ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="sr-only">{label ?? t("label")}</legend>
          {items.map((item) => {
            const born = item.birth ? displayDate(item.birth, locale) : null;
            return (
              <label key={item.id} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 hover:bg-amate">
                <input
                  type="radio"
                  name={`${name}-choice`}
                  value={item.id}
                  className="size-5 accent-accent"
                  onChange={() => choose({ id: item.id, display_name: item.display_name })}
                />
                <span>
                  <span className="font-semibold">{item.display_name}</span>
                  {born ? <span className="fh-date ml-2 text-muted">{born}</span> : null}
                </span>
              </label>
            );
          })}
        </fieldset>
      ) : null}
    </div>
  );
}

function resultMessage(
  result: PeopleSearchResult | null,
  count: number,
  t: ReturnType<typeof useTranslations<"family.picker">>,
  errors: (code: ErrorCode) => string,
): string {
  if (!result) return "";
  if (!result.ok) return t("failed", { error: errors(result.code) });
  return count === 0 ? t("noResults") : t("results", { count });
}
