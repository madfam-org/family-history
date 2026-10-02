"use client";

import { useTranslations } from "next-intl";
import { useActionState, useId, useState } from "react";

import { addAssociationAction, removeAssociationAction } from "@/app/actions/relatives";
import type { AssociationRole, Sex } from "@/lib/api/schemas";
import { ASSOCIATION_ROLES, associationNeedsPhrase, godparentLabelKey, PHRASE_MAX } from "@/lib/forms/family";
import { idleEditorState, type EditorState } from "@/lib/forms/types";

import { ConfirmRemove } from "./ConfirmRemove";
import { FormStatus, stateValue } from "./FormStatus";
import { PersonPicker } from "./PersonPicker";

export interface GodparentEntry {
  id: string;
  personId: string;
  name: string;
  sex: Sex;
  role: string;
  phrase: string | null;
}

/**
 * Padrinos y madrinas of one sacramental event (bautizo, confirmación, primera comunión,
 * matrimonio religioso, XV años), plus witnesses and officiants. Padrino or madrina follows the
 * godparent's recorded sex.
 */
export function GodparentsEditor({
  spaceId,
  eventId,
  principalId,
  entries,
}: {
  spaceId: string;
  eventId: string;
  principalId: string;
  entries: readonly GodparentEntry[];
}) {
  const t = useTranslations("family.godparents");
  const relationships = useTranslations("family.relationships");
  const [state, action, pending] = useActionState<EditorState, FormData>(addAssociationAction, idleEditorState);
  const [role, setRole] = useState<AssociationRole>((stateValue(state, "role", "godparent") as AssociationRole) || "godparent");
  const phraseId = useId();
  const phraseHintId = useId();
  const formKey = state.status === "saved" ? `saved-${state.count}` : "editing";

  function label(entry: GodparentEntry): string {
    // A recorded phrase («padrino de anillos») says more than the role's generic name.
    if (entry.phrase) return entry.phrase;
    if (entry.role === "godparent") return t(godparentLabelKey(entry.sex));
    return ASSOCIATION_ROLES.includes(entry.role as AssociationRole) ? t(`roles.${entry.role as AssociationRole}`) : entry.role;
  }

  return (
    <div className="mt-2 flex flex-col gap-3 border-l-4 border-amate pl-3">
      <h4 className="font-semibold">{t("title")}</h4>
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {entries.map((entry) => (
            <li key={entry.id} className="flex flex-col gap-1">
              <p>
                <span className="text-sm text-muted">{label(entry)}: </span>
                <span className="font-semibold">{entry.name}</span>
              </p>
              <ConfirmRemove
                action={removeAssociationAction}
                field="associationId"
                id={entry.id}
                label={t("removeLabel", { name: entry.name })}
                question={t("confirmRemove", { name: entry.name })}
                done={t("removed")}
              />
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-accent">{t("addTitle")}</summary>
        <form key={formKey} action={action} className="mt-2 flex flex-col gap-3">
          <input type="hidden" name="spaceId" value={spaceId} />
          <input type="hidden" name="eventId" value={eventId} />
          <fieldset className="flex flex-col gap-1">
            <legend className="font-semibold">{t("role")}</legend>
            <div className="flex flex-wrap gap-x-6">
              {ASSOCIATION_ROLES.map((value) => (
                <label key={value} className="inline-flex min-h-11 items-center gap-2">
                  <input
                    type="radio"
                    name="role"
                    value={value}
                    checked={role === value}
                    onChange={() => setRole(value)}
                    className="size-5 accent-accent"
                  />
                  {t(`roles.${value}`)}
                </label>
              ))}
            </div>
          </fieldset>
          {associationNeedsPhrase(role) || role === "godparent" ? (
            <div className="flex flex-col gap-1">
              <label htmlFor={phraseId} className="font-semibold">
                {associationNeedsPhrase(role) ? t("phrase") : t("phraseOptional")}
              </label>
              <input
                id={phraseId}
                name="phrase"
                maxLength={PHRASE_MAX}
                required={associationNeedsPhrase(role)}
                defaultValue={stateValue(state, "phrase")}
                aria-describedby={phraseHintId}
                className="fh-input"
              />
              <p id={phraseHintId} className="text-sm text-muted">
                {t("phraseHint")}
              </p>
            </div>
          ) : null}
          <PersonPicker spaceId={spaceId} name="relativeId" excludeId={principalId} />
          <FormStatus
            state={state}
            saved={t("added")}
            invalid={(error) =>
              error === "phraseRequired"
                ? t("phraseRequired")
                : error === "pickRequired"
                  ? relationships("pickRequired")
                  : undefined
            }
          />
          <button type="submit" className="fh-button self-start" disabled={pending}>
            {pending ? t("submitting") : t("submit")}
          </button>
        </form>
      </details>
    </div>
  );
}
