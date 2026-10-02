"use client";

import { useTranslations } from "next-intl";
import { useActionState, useId, useState } from "react";

import { updateNamesAction } from "@/app/actions/person-editor";
import { NAME_PART_MAX, PARTICLE_MAX, previewName, SURNAME_ORDERS, type NameValues } from "@/lib/forms/names";
import { idleEditorState, type EditorState } from "@/lib/forms/types";

import { FormStatus } from "./FormStatus";

const SEXES = ["U", "F", "M", "X"] as const;
type TextKey = Exclude<keyof NameValues, "surnameOrder" | "sex">;

function Field({
  field,
  label,
  hint,
  max,
  value,
  onChange,
}: {
  field: TextKey;
  label: string;
  hint?: string;
  max: number;
  value: string;
  onChange: (field: TextKey, value: string) => void;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {label}
      </label>
      <input
        id={id}
        name={field}
        value={value}
        maxLength={max}
        autoComplete="off"
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(field, event.target.value)}
        className="fh-input"
      />
      {hint ? (
        <p id={hintId} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** The Mexican name model, with a live preview of the name in the chosen surname order. */
export function NameEditorForm({
  personId,
  initial,
  sexLabels,
}: {
  personId: string;
  initial: NameValues;
  sexLabels: Record<(typeof SEXES)[number], string>;
}) {
  const t = useTranslations("family.editor");
  const [state, action, pending] = useActionState<EditorState, FormData>(updateNamesAction, idleEditorState);
  const [values, setValues] = useState<NameValues>(initial);
  const set = (field: keyof NameValues, value: string) => setValues((current) => ({ ...current, [field]: value }));
  const preview = previewName(values);

  return (
    <form action={action} className="fh-card flex flex-col gap-4" aria-labelledby="editar-nombre">
      <h2 id="editar-nombre" className="text-xl font-bold">
        {t("namesTitle")}
      </h2>
      <p className="text-muted">{t("namesLead")}</p>
      <input type="hidden" name="personId" value={personId} />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field field="given" label={t("given")} max={NAME_PART_MAX} value={values.given} onChange={set} />
        </div>
        <Field field="paternal" label={t("paternal")} max={NAME_PART_MAX} value={values.paternal} onChange={set} />
        <Field field="maternal" label={t("maternal")} max={NAME_PART_MAX} value={values.maternal} onChange={set} />
        <Field
          field="particlePaternal"
          label={t("particlePaternal")}
          hint={t("particleHint")}
          max={PARTICLE_MAX}
          value={values.particlePaternal}
          onChange={set}
        />
        <Field
          field="particleMaternal"
          label={t("particleMaternal")}
          hint={t("particleHint")}
          max={PARTICLE_MAX}
          value={values.particleMaternal}
          onChange={set}
        />
        <Field
          field="nombreUsado"
          label={t("nombreUsado")}
          hint={t("nombreUsadoHint")}
          max={NAME_PART_MAX}
          value={values.nombreUsado}
          onChange={set}
        />
        <Field
          field="nicknames"
          label={t("nicknames")}
          hint={t("nicknamesHint")}
          max={NAME_PART_MAX * 4}
          value={values.nicknames}
          onChange={set}
        />
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="font-semibold">{t("surnameOrder")}</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          {SURNAME_ORDERS.map((order) => (
            <label key={order} className="inline-flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name="surnameOrder"
                value={order}
                checked={values.surnameOrder === order}
                onChange={() => set("surnameOrder", order)}
                className="size-5 accent-accent"
              />
              {t(`surnameOrders.${order}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="font-semibold">{t("sex")}</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          {SEXES.map((sex) => (
            <label key={sex} className="inline-flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name="sex"
                value={sex}
                checked={values.sex === sex}
                onChange={() => set("sex", sex)}
                className="size-5 accent-accent"
              />
              {sexLabels[sex]}
            </label>
          ))}
        </div>
      </fieldset>
      {preview ? (
        <p className="rounded-lg bg-amate p-3 text-bark" aria-live="polite">
          {t("preview", { name: preview })}
        </p>
      ) : null}
      <FormStatus state={state} saved={t("saved")} invalid={(error) => t(`errors.${error as "nameRequired"}`)} />
      <button type="submit" className="fh-button self-start" disabled={pending}>
        {pending ? t("saving") : t("save")}
      </button>
    </form>
  );
}
