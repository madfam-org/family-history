"use client";

import { useTranslations } from "next-intl";
import { useActionState, useEffect, useRef, useState } from "react";

import { idleEditorState, type EditorState } from "@/lib/forms/types";

import { FormStatus } from "./FormStatus";

type RemoveAction = (previous: EditorState, form: FormData) => Promise<EditorState>;

/**
 * A two-step removal: the first button asks, the second removes. Focus moves to the question
 * and back to the first button on «Cancelar», so keyboard and screen-reader users never lose
 * their place.
 */
export function ConfirmRemove({
  action,
  field,
  id,
  label,
  question,
  done,
}: {
  action: RemoveAction;
  field: string;
  id: string;
  label: string;
  question: string;
  done: string;
}) {
  const t = useTranslations("family.relationships");
  const [state, formAction, pending] = useActionState<EditorState, FormData>(action, idleEditorState);
  const [asking, setAsking] = useState(false);
  const questionRef = useRef<HTMLParagraphElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const wasAsking = useRef(false);

  useEffect(() => {
    if (asking) questionRef.current?.focus();
    else if (wasAsking.current) openerRef.current?.focus();
    wasAsking.current = asking;
  }, [asking]);

  if (!asking) {
    return (
      <div className="flex flex-col gap-1">
        <button
          ref={openerRef}
          type="button"
          aria-label={label}
          className="fh-button fh-button-secondary self-start"
          onClick={() => setAsking(true)}
        >
          {t("remove")}
        </button>
        {state.status !== "idle" ? <FormStatus state={state} saved={done} /> : null}
      </div>
    );
  }

  return (
    <form action={formAction} className="flex flex-col gap-2 rounded-lg border-2 border-danger p-3">
      <input type="hidden" name={field} value={id} />
      <p ref={questionRef} tabIndex={-1} className="font-semibold">
        {question}
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="fh-button" disabled={pending}>
          {pending ? t("removing") : t("confirmYes")}
        </button>
        <button type="button" className="fh-button fh-button-secondary" onClick={() => setAsking(false)}>
          {t("cancel")}
        </button>
      </div>
      <FormStatus state={state} saved={done} />
    </form>
  );
}
