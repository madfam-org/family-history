"use client";

import { useActionState, useId } from "react";

import { createSpaceAction } from "@/app/actions/spaces";
import type { ErrorCode } from "@/lib/api/errors";
import type { SpaceFormError } from "@/lib/forms/space";
import { idleFormState, type SpaceFormState } from "@/lib/forms/types";

export interface CreateSpaceCopy {
  title: string;
  nameLabel: string;
  nameHint: string;
  create: string;
  creating: string;
  invalid: Record<SpaceFormError, string>;
  failed: Partial<Record<ErrorCode, string>> & { unknown: string };
}

export function CreateSpaceForm({ locale, copy }: { locale: string; copy: CreateSpaceCopy }) {
  const [state, formAction, pending] = useActionState<SpaceFormState, FormData>(createSpaceAction, idleFormState);
  const nameId = useId();
  const hintId = useId();
  const errorId = useId();
  const message =
    state.status === "invalid"
      ? copy.invalid[state.error]
      : state.status === "failed"
        ? (copy.failed[state.code] ?? copy.failed.unknown)
        : undefined;

  return (
    <form action={formAction} className="fh-card flex flex-col gap-4">
      <h2 className="text-xl font-bold">{copy.title}</h2>
      <input type="hidden" name="locale" value={locale} />
      <div className="flex flex-col gap-1">
        <label htmlFor={nameId} className="font-semibold">
          {copy.nameLabel}
        </label>
        <input
          id={nameId}
          name="name"
          required
          maxLength={120}
          autoComplete="off"
          defaultValue={state.status === "idle" ? "" : state.values.name}
          aria-describedby={message ? `${hintId} ${errorId}` : hintId}
          aria-invalid={state.status === "invalid" || undefined}
          className="fh-input"
        />
        <p id={hintId} className="text-sm text-muted">
          {copy.nameHint}
        </p>
      </div>
      {message ? (
        <p id={errorId} role="alert" className="font-semibold text-danger">
          {message}
        </p>
      ) : null}
      <button type="submit" className="fh-button self-start" disabled={pending}>
        {pending ? copy.creating : copy.create}
      </button>
    </form>
  );
}
