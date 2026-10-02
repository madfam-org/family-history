"use client";

import { useTranslations } from "next-intl";

import type { EditorState } from "@/lib/forms/types";

/**
 * The visible outcome of an editor: an alert for failures (mapped error copy, never the API's
 * English message) and a polite status for success. `invalid` errors are looked up under the
 * editor's own namespace by the caller.
 */
export function FormStatus({
  state,
  saved,
  invalid,
}: {
  state: EditorState;
  saved: string;
  /** Copy for the editor's own validation errors; undefined falls back to the generic one. */
  invalid?: (error: string) => string | undefined;
}) {
  const errors = useTranslations("errors");
  if (state.status === "failed") {
    // A refused date is explained next to the date field itself.
    if (state.dateHint) return null;
    return (
      <p role="alert" className="font-semibold text-danger">
        {errors(state.code)}
      </p>
    );
  }
  if (state.status === "invalid") {
    return (
      <p role="alert" className="font-semibold text-danger">
        {invalid?.(state.error) ?? errors("validation_error")}
      </p>
    );
  }
  return (
    <p role="status" aria-live="polite" className="text-success">
      {state.status === "saved" ? saved : ""}
    </p>
  );
}

export function stateValue(state: EditorState, key: string, fallback = ""): string {
  if (state.status === "invalid" || state.status === "failed") return state.values[key] ?? fallback;
  return fallback;
}
