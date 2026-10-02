import "server-only";

import { errorMessageKey, isApiError } from "@/lib/api/errors";
import { dateHint, isDateErrorCode } from "@/lib/dates/hints";
import type { EditorState } from "@/lib/forms/types";

/**
 * Turns an API failure into a visible editor state. A refused free-text date gets the hint
 * chosen for exactly what was typed. Anything that is not an `ApiError` is rethrown.
 */
export function failedState(
  error: unknown,
  values: Record<string, string>,
  options: { dateText?: string; createdId?: string } = {},
): EditorState {
  if (!isApiError(error)) throw error;
  const code = errorMessageKey(error.code);
  const state: EditorState = { status: "failed", code, values };
  if (options.createdId) state.createdId = options.createdId;
  if (isDateErrorCode(code) && options.dateText) state.dateHint = dateHint(options.dateText, code);
  return state;
}

export function savedState(previous: EditorState, createdId?: string): EditorState {
  const count = previous.status === "saved" ? previous.count + 1 : 1;
  return createdId ? { status: "saved", count, createdId } : { status: "saved", count };
}

export function field(form: FormData, name: string): string {
  return String(form.get(name) ?? "")
    .trim()
    .replace(/\s+/g, " ");
}
