/**
 * Free-text dates (addendum A). The API parses what people type («hacia 1890», «15 de marzo de
 * 1923») with the domain's `parse_user_date_es`, which never guesses. When it refuses, it answers
 * `422 ambiguous_date` or `422 invalid_date`; this module picks the most helpful hint for the
 * text that was typed. Pure: no React, no Next.js.
 *
 * The rules mirror docs/lanes/domain.md §Dates → User input: numeric dates are read
 * day/month/year, a month above 12 is an error, two-digit years are rejected, and «1890-1895» is
 * ambiguous (a range or a period).
 */

export type DateErrorCode = "ambiguous_date" | "invalid_date";

export type DateHintKey =
  | "yearSpan"
  | "ambiguous"
  | "twoDigitYear"
  | "monthOver12"
  | "weekday"
  | "invalid";

export function isDateErrorCode(code: string): code is DateErrorCode {
  return code === "ambiguous_date" || code === "invalid_date";
}

const YEAR_SPAN = /^\s*(\d{3,4})\s*[-–—/]\s*(\d{3,4})\s*$/;
const NUMERIC = /^\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,4})\s*$/;
const WEEKDAY = /\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i;

export interface DateHint {
  key: DateHintKey;
  /** Values for the message placeholders, when the hint can quote the input back. */
  values: Record<string, string>;
}

/** Chooses the hint for a refused date. The typed text never leaves the page through this. */
export function dateHint(text: string, code: DateErrorCode): DateHint {
  const span = YEAR_SPAN.exec(text);
  if (span) return { key: "yearSpan", values: { from: span[1] ?? "", to: span[2] ?? "" } };

  const numeric = NUMERIC.exec(text);
  if (numeric) {
    const [, day = "", month = "", year = ""] = numeric;
    if (year.length <= 2) return { key: "twoDigitYear", values: { year } };
    if (Number(month) > 12) return { key: "monthOver12", values: { day, month } };
  }
  if (WEEKDAY.test(text) && code === "invalid_date") return { key: "weekday", values: {} };
  return { key: code === "ambiguous_date" ? "ambiguous" : "invalid", values: {} };
}

/** Example inputs shown under every date field, in the order they are listed. */
export const DATE_EXAMPLE_KEYS = ["exact", "about", "before", "between", "monthYear"] as const;

export type DateDisplayLocale = "es" | "en";

/**
 * The text to show for an event's date: the API's humanized date in the page language, else the
 * text as the family wrote it, else the canonical GEDCOM value, else null («Fecha desconocida»).
 */
export function displayDate(
  event: {
    date_display?: { es: string; en: string } | null | undefined;
    date_original?: string | null | undefined;
    date_value?: string | null | undefined;
  },
  locale: DateDisplayLocale,
): string | null {
  const humanized = event.date_display?.[locale];
  if (humanized) return humanized;
  if (event.date_original) return event.date_original;
  return event.date_value ?? null;
}

/** Trims and collapses spaces; the API keeps `date_original` exactly as sent. */
export function normalizeDateInput(text: string): string {
  return text.trim().replace(/\s+/g, " ");
}

export const DATE_INPUT_MAX = 80;
