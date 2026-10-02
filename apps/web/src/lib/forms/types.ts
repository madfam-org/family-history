/** Form action states shared by server actions and client forms (no server imports). */
import type { ErrorCode } from "@/lib/api/errors";
import type { DateHint } from "@/lib/dates/hints";

import type { PersonFormError } from "./person";
import type { SpaceFormError } from "./space";

export type FormState<E extends string> =
  | { status: "idle" }
  | { status: "invalid"; error: E; values: Record<string, string> }
  | { status: "failed"; code: ErrorCode; values: Record<string, string> };

export type SpaceFormState = FormState<SpaceFormError>;
export type PersonFormState = FormState<PersonFormError>;

export const idleFormState = { status: "idle" } as const;

/**
 * State of the wave-2 editors (names, events, relationships, godparents). `saved` carries a
 * counter so a second identical save still announces itself; a refused date carries the hint
 * chosen for the text that was typed.
 */
export type EditorState =
  | { status: "idle" }
  | { status: "saved"; count: number; createdId?: string }
  | { status: "invalid"; error: string; values: Record<string, string> }
  | {
      status: "failed";
      code: ErrorCode;
      values: Record<string, string>;
      dateHint?: DateHint;
      /** Set when a new person was created but the step after it failed. */
      createdId?: string;
    };

export const idleEditorState: EditorState = { status: "idle" };
