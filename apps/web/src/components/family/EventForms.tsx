"use client";

import { useTranslations } from "next-intl";
import { useActionState, useId, useState } from "react";

import { addEventAction, correctEventDateAction } from "@/app/actions/person-editor";
import { DESCRIPTION_MAX, EDITABLE_EVENT_TYPES, takesSpouse } from "@/lib/forms/family";
import { idleEditorState, type EditorState } from "@/lib/forms/types";

import { DateField } from "./DateField";
import { FormStatus, stateValue } from "./FormStatus";

export interface PartnerOption {
  id: string;
  name: string;
}

/** «Agregar evento»: type, free-text date, notes and, for marriages, the spouse. */
export function AddEventForm({
  personId,
  spaceId,
  partners,
  defaultType = "birth",
}: {
  personId: string;
  spaceId: string;
  partners: readonly PartnerOption[];
  defaultType?: string;
}) {
  const t = useTranslations("family.events");
  const [state, action, pending] = useActionState<EditorState, FormData>(addEventAction, idleEditorState);
  const [type, setType] = useState(stateValue(state, "type", defaultType));
  const typeId = useId();
  const spouseId = useId();
  const descriptionId = useId();
  const descriptionHintId = useId();
  const hint = state.status === "failed" ? state.dateHint : undefined;
  // A saved event resets the form (a new key remounts the uncontrolled fields).
  const formKey = state.status === "saved" ? `saved-${state.count}` : "editing";

  return (
    <form key={formKey} action={action} className="fh-card flex flex-col gap-4" aria-labelledby="agregar-evento">
      <h2 id="agregar-evento" className="text-xl font-bold">
        {t("addTitle")}
      </h2>
      <input type="hidden" name="personId" value={personId} />
      <input type="hidden" name="spaceId" value={spaceId} />
      <div className="flex flex-col gap-1">
        <label htmlFor={typeId} className="font-semibold">
          {t("type")}
        </label>
        <select id={typeId} name="type" value={type} onChange={(event) => setType(event.target.value)} className="fh-input">
          {EDITABLE_EVENT_TYPES.map((value) => (
            <option key={value} value={value}>
              {t(`types.${value}`)}
            </option>
          ))}
        </select>
      </div>
      <DateField name="date" label={t("date")} defaultValue={stateValue(state, "date")} hint={hint} />
      {takesSpouse(type) && partners.length > 0 ? (
        <div className="flex flex-col gap-1">
          <label htmlFor={spouseId} className="font-semibold">
            {t("spouse")}
          </label>
          <select id={spouseId} name="spouseId" defaultValue={stateValue(state, "spouseId")} className="fh-input">
            <option value="">{t("spouseNone")}</option>
            {partners.map((partner) => (
              <option key={partner.id} value={partner.id}>
                {partner.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="flex flex-col gap-1">
        <label htmlFor={descriptionId} className="font-semibold">
          {t("description")}
        </label>
        <textarea
          id={descriptionId}
          name="description"
          rows={2}
          maxLength={DESCRIPTION_MAX}
          defaultValue={stateValue(state, "description")}
          aria-describedby={descriptionHintId}
          className="fh-input"
        />
        <p id={descriptionHintId} className="text-sm text-muted">
          {t("descriptionHint")}
        </p>
      </div>
      <FormStatus state={state} saved={t("saved")} />
      <button type="submit" className="fh-button self-start" disabled={pending}>
        {pending ? t("saving") : t("save")}
      </button>
    </form>
  );
}

/** «Corregir fecha»: a disclosure under one event. */
export function CorrectDateForm({ eventId, current }: { eventId: string; current: string }) {
  const t = useTranslations("family.events");
  const [state, action, pending] = useActionState<EditorState, FormData>(correctEventDateAction, idleEditorState);
  const hint = state.status === "failed" ? state.dateHint : undefined;
  return (
    <details className="mt-1" open={state.status === "failed" || state.status === "invalid" ? true : undefined}>
      <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm font-semibold text-accent">
        {t("correctDate")}
      </summary>
      <form action={action} className="mt-2 flex flex-col gap-3">
        <input type="hidden" name="eventId" value={eventId} />
        <DateField name="date" label={t("date")} defaultValue={stateValue(state, "date", current)} hint={hint} required />
        <FormStatus state={state} saved={t("dateSaved")} invalid={(error) => (error === "dateRequired" ? t("dateRequired") : undefined)} />
        <button type="submit" className="fh-button fh-button-secondary self-start" disabled={pending}>
          {t("correctDateSubmit")}
        </button>
      </form>
    </details>
  );
}
