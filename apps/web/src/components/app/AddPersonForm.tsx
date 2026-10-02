"use client";

import { useActionState, useId } from "react";

import { createPersonAction } from "@/app/actions/people";
import type { ErrorCode } from "@/lib/api/errors";
import type { Sex } from "@/lib/api/schemas";
import type { PersonFormError } from "@/lib/forms/person";
import { idleFormState, type PersonFormState } from "@/lib/forms/types";

export interface AddPersonCopy {
  title: string;
  lead: string;
  given: string;
  paternal: string;
  maternal: string;
  nickname: string;
  nicknameHint: string;
  sex: string;
  sexOptions: Record<Sex, string>;
  birthDate: string;
  birthDateHint: string;
  submit: string;
  submitting: string;
  invalid: Record<PersonFormError, string>;
  failed: Partial<Record<ErrorCode, string>> & { unknown: string };
}

const SEXES: readonly Sex[] = ["U", "F", "M", "X"];

function TextField(props: {
  name: string;
  label: string;
  hint?: string;
  maxLength: number;
  defaultValue: string;
  autoComplete?: string;
  className?: string;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className={`flex flex-col gap-1 ${props.className ?? ""}`}>
      <label htmlFor={id} className="font-semibold">
        {props.label}
      </label>
      <input
        id={id}
        name={props.name}
        maxLength={props.maxLength}
        defaultValue={props.defaultValue}
        autoComplete={props.autoComplete ?? "off"}
        aria-describedby={props.hint ? hintId : undefined}
        className="fh-input"
      />
      {props.hint ? (
        <p id={hintId} className="text-sm text-muted">
          {props.hint}
        </p>
      ) : null}
    </div>
  );
}

export function AddPersonForm({ locale, spaceId, copy }: { locale: string; spaceId: string; copy: AddPersonCopy }) {
  const [state, formAction, pending] = useActionState<PersonFormState, FormData>(createPersonAction, idleFormState);
  const values: Record<string, string> = state.status === "idle" ? {} : state.values;
  const message =
    state.status === "invalid"
      ? copy.invalid[state.error]
      : state.status === "failed"
        ? (copy.failed[state.code] ?? copy.failed.unknown)
        : undefined;
  const value = (key: string) => values[key] ?? "";

  return (
    <form action={formAction} className="fh-card flex flex-col gap-4" aria-describedby="agregar-persona-lead">
      <h2 className="text-xl font-bold">{copy.title}</h2>
      <p id="agregar-persona-lead" className="text-muted">
        {copy.lead}
      </p>
      <input type="hidden" name="locale" value={locale} />
      <input type="hidden" name="spaceId" value={spaceId} />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField name="given" label={copy.given} maxLength={120} defaultValue={value("given")} className="sm:col-span-2" />
        <TextField name="paternal" label={copy.paternal} maxLength={120} defaultValue={value("paternal")} />
        <TextField name="maternal" label={copy.maternal} maxLength={120} defaultValue={value("maternal")} />
        <TextField
          name="nickname"
          label={copy.nickname}
          hint={copy.nicknameHint}
          maxLength={120}
          defaultValue={value("nickname")}
        />
        <TextField
          name="birthDate"
          label={copy.birthDate}
          hint={copy.birthDateHint}
          maxLength={80}
          defaultValue={value("birthDate")}
        />
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="font-semibold">{copy.sex}</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {SEXES.map((sex) => (
            <label key={sex} className="inline-flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name="sex"
                value={sex}
                defaultChecked={(value("sex") || "U") === sex}
                className="size-5 accent-accent"
              />
              {copy.sexOptions[sex]}
            </label>
          ))}
        </div>
      </fieldset>
      {message ? (
        <p role="alert" className="font-semibold text-danger">
          {message}
        </p>
      ) : null}
      <button type="submit" className="fh-button self-start" disabled={pending}>
        {pending ? copy.submitting : copy.submit}
      </button>
    </form>
  );
}
