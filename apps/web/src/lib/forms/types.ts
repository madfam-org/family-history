/** Form action states shared by server actions and client forms (no server imports). */
import type { ErrorCode } from "@/lib/api/errors";

import type { PersonFormError } from "./person";
import type { SpaceFormError } from "./space";

export type FormState<E extends string> =
  | { status: "idle" }
  | { status: "invalid"; error: E; values: Record<string, string> }
  | { status: "failed"; code: ErrorCode; values: Record<string, string> };

export type SpaceFormState = FormState<SpaceFormError>;
export type PersonFormState = FormState<PersonFormError>;

export const idleFormState = { status: "idle" } as const;
