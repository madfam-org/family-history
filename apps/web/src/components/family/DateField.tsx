"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";

import { DATE_EXAMPLE_KEYS, DATE_INPUT_MAX, type DateHint } from "@/lib/dates/hints";

/**
 * A free-text date input (addendum A). It always lists examples of what can be typed, and when
 * the API refused the last attempt it shows the hint chosen for that text, linked to the input
 * with aria-describedby and announced as an alert.
 */
export function DateField({
  name,
  label,
  defaultValue,
  hint,
  required = false,
}: {
  name: string;
  label: string;
  defaultValue: string;
  hint?: DateHint | undefined;
  required?: boolean;
}) {
  const t = useTranslations("family.dates");
  const id = useId();
  const examplesId = useId();
  const hintId = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {label}
      </label>
      <input
        id={id}
        name={name}
        defaultValue={defaultValue}
        maxLength={DATE_INPUT_MAX}
        autoComplete="off"
        inputMode="text"
        required={required}
        aria-invalid={hint ? true : undefined}
        aria-describedby={hint ? `${hintId} ${examplesId}` : examplesId}
        className="fh-input"
      />
      {hint ? (
        <p id={hintId} role="alert" className="font-semibold text-danger">
          {t(`hints.${hint.key}`, hint.values)}
        </p>
      ) : null}
      <div id={examplesId} className="text-sm text-muted">
        <p>{t("examplesTitle")}</p>
        <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
          {DATE_EXAMPLE_KEYS.map((key) => (
            <li key={key} className="fh-date">
              {t(`examples.${key}`)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
