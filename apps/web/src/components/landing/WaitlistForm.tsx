"use client";

import { useActionState, useId } from "react";

import { joinWaitlistAction } from "@/app/actions/waitlist";
import type { Locale } from "@/i18n/locales";
import { initialWaitlistResult, type WaitlistError } from "@/lib/waitlist/types";

export interface WaitlistCopy {
  title: string;
  lead: string;
  emailLabel: string;
  emailHint: string;
  consentBefore: string;
  consentLink: string;
  consentAfter: string;
  submit: string;
  submitting: string;
  successTitle: string;
  successBody: string;
  errors: Record<WaitlistError, string>;
}

export function WaitlistForm({ locale, copy }: { locale: Locale; copy: WaitlistCopy }) {
  const [state, formAction, pending] = useActionState(joinWaitlistAction, initialWaitlistResult);
  const emailId = useId();
  const hintId = useId();
  const errorId = useId();
  const consentId = useId();

  if (state.status === "success") {
    return (
      <div role="status" className="fh-card">
        <p className="text-xl font-bold text-success">{copy.successTitle}</p>
        <p className="mt-2">{copy.successBody}</p>
      </div>
    );
  }

  const error = state.status === "error" ? state.error : undefined;
  return (
    <form action={formAction} className="fh-card flex flex-col gap-4" noValidate>
      <h3 className="text-2xl font-bold">{copy.title}</h3>
      <p className="text-muted">{copy.lead}</p>
      <input type="hidden" name="locale" value={locale} />
      <div className="flex flex-col gap-1">
        <label htmlFor={emailId} className="font-semibold">
          {copy.emailLabel}
        </label>
        <input
          id={emailId}
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          required
          maxLength={254}
          defaultValue={state.status === "error" ? state.email : ""}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error === "invalidEmail" || undefined}
          className="fh-input"
        />
        <p id={hintId} className="text-sm text-muted">
          {copy.emailHint}
        </p>
      </div>
      <div className="flex items-start gap-3">
        <input
          id={consentId}
          name="consent"
          type="checkbox"
          required
          defaultChecked={false}
          aria-invalid={error === "consentRequired" || undefined}
          className="mt-1 size-5 shrink-0 accent-accent"
        />
        <label htmlFor={consentId}>
          {copy.consentBefore}
          <a href={`/${locale}/aviso-de-privacidad`} target="_blank" rel="noopener">
            {copy.consentLink}
          </a>
          {copy.consentAfter}
        </label>
      </div>
      {error ? (
        <p id={errorId} role="alert" className="font-semibold text-danger">
          {copy.errors[error]}
        </p>
      ) : null}
      <button type="submit" className="fh-button self-start" disabled={pending} aria-disabled={pending}>
        {pending ? copy.submitting : copy.submit}
      </button>
    </form>
  );
}
