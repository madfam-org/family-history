"use client";

import { useLocale, useTranslations } from "next-intl";
import { useActionState, useId, useState } from "react";

import { addRelativeAction } from "@/app/actions/relatives";
import { PARTNER_STATUSES, PEDIGREES } from "@/lib/api/schemas";
import { RELATIVE_KINDS, type RelativeKind } from "@/lib/forms/family";
import { PERSON_FIELD_MAX } from "@/lib/forms/person";
import { idleEditorState, type EditorState } from "@/lib/forms/types";

import { FormStatus, stateValue } from "./FormStatus";
import { PersonPicker } from "./PersonPicker";

function Radio({ name, value, checked, onChange, label }: {
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <label className="inline-flex min-h-11 items-center gap-2">
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} className="size-5 accent-accent" />
      {label}
    </label>
  );
}

function TextInput({ name, label, defaultValue }: { name: string; label: string; defaultValue: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {label}
      </label>
      <input id={id} name={name} maxLength={PERSON_FIELD_MAX} defaultValue={defaultValue} autoComplete="off" className="fh-input" />
    </div>
  );
}

/**
 * «Agregar familiar»: father, mother, child or partner, with the pedigree (birth, adopted,
 * foster, step) or the partner status, by picking someone in the tree or creating them here.
 */
export function AddRelativeForm({ personId, spaceId, nameLabels }: {
  personId: string;
  spaceId: string;
  nameLabels: { given: string; paternal: string; maternal: string };
}) {
  const t = useTranslations("family.relationships");
  const errors = useTranslations("errors");
  const editor = useTranslations("family.editor");
  const locale = useLocale();
  const [state, action, pending] = useActionState<EditorState, FormData>(addRelativeAction, idleEditorState);
  const [kind, setKind] = useState<RelativeKind>((stateValue(state, "kind", "father") as RelativeKind) || "father");
  const [pedigree, setPedigree] = useState(stateValue(state, "pedigree", "birth"));
  const [status, setStatus] = useState(stateValue(state, "status", "married"));
  const [mode, setMode] = useState(stateValue(state, "mode", "existing"));
  const formKey = state.status === "saved" ? `saved-${state.count}` : "editing";
  const createdId = state.status === "failed" ? state.createdId : undefined;

  return (
    <form key={formKey} action={action} className="fh-card flex flex-col gap-4" aria-labelledby="agregar-familiar">
      <h2 id="agregar-familiar" className="text-xl font-bold">
        {t("addTitle")}
      </h2>
      <input type="hidden" name="personId" value={personId} />
      <input type="hidden" name="spaceId" value={spaceId} />
      <fieldset className="flex flex-col gap-1">
        <legend className="font-semibold">{t("kind")}</legend>
        <div className="flex flex-wrap gap-x-6">
          {RELATIVE_KINDS.map((value) => (
            <Radio key={value} name="kind" value={value} checked={kind === value} onChange={() => setKind(value)} label={t(`kinds.${value}`)} />
          ))}
        </div>
      </fieldset>
      {kind === "partner" ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="font-semibold">{t("status")}</legend>
          <div className="flex flex-wrap gap-x-6">
            {PARTNER_STATUSES.map((value) => (
              <Radio key={value} name="status" value={value} checked={status === value} onChange={() => setStatus(value)} label={t(`statuses.${value}`)} />
            ))}
          </div>
          <p className="text-sm text-muted">{t("statusHint")}</p>
        </fieldset>
      ) : (
        <fieldset className="flex flex-col gap-1">
          <legend className="font-semibold">{t("pedigree")}</legend>
          <div className="flex flex-col">
            {PEDIGREES.map((value) => (
              <Radio key={value} name="pedigree" value={value} checked={pedigree === value} onChange={() => setPedigree(value)} label={t(`pedigrees.${value}`)} />
            ))}
          </div>
        </fieldset>
      )}
      <fieldset className="flex flex-col gap-1">
        <legend className="font-semibold">{t("who")}</legend>
        <div className="flex flex-wrap gap-x-6">
          <Radio name="mode" value="existing" checked={mode === "existing"} onChange={() => setMode("existing")} label={t("pickExisting")} />
          <Radio name="mode" value="new" checked={mode === "new"} onChange={() => setMode("new")} label={t("createNew")} />
        </div>
      </fieldset>
      {mode === "existing" ? (
        <PersonPicker spaceId={spaceId} name="relativeId" excludeId={personId} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <p className="text-muted sm:col-span-2">{t("newPersonLead")}</p>
          <div className="sm:col-span-2">
            <TextInput name="given" label={nameLabels.given} defaultValue={stateValue(state, "given")} />
          </div>
          <TextInput name="paternal" label={nameLabels.paternal} defaultValue={stateValue(state, "paternal")} />
          <TextInput name="maternal" label={nameLabels.maternal} defaultValue={stateValue(state, "maternal")} />
        </div>
      )}
      {createdId ? (
        <p role="alert" className="font-semibold text-danger">
          {t("createdWithoutLink", { error: errors(state.status === "failed" ? state.code : "unknown") })}{" "}
          <a href={`/${locale}/personas/${encodeURIComponent(createdId)}`}>{t("openCreated")}</a>
        </p>
      ) : (
        <FormStatus
          state={state}
          saved={t("added")}
          invalid={(error) => {
            if (error === "pickRequired" || error === "samePerson") return t(error);
            if (error === "nameRequired" || error === "tooLong") return editor(`errors.${error}`);
            return undefined;
          }}
        />
      )}
      <button type="submit" className="fh-button self-start" disabled={pending}>
        {pending ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}
