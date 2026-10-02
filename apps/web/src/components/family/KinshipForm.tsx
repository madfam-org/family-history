"use client";

import { useTranslations } from "next-intl";

import { PersonPicker, type PickedPerson } from "./PersonPicker";

/**
 * «¿Cómo estamos emparentados?»: two pickers in a GET form, so the answer has its own URL
 * (`?de=<id>&a=<id>`, ids only) and works without JavaScript once both people are chosen.
 */
export function KinshipForm({
  action,
  spaceId,
  ego,
  alter,
}: {
  action: string;
  spaceId: string;
  ego: PickedPerson | null;
  alter: PickedPerson | null;
}) {
  const t = useTranslations("family.kinship");
  return (
    <form method="get" action={action} className="fh-card flex flex-col gap-4">
      <PersonPicker spaceId={spaceId} name="de" label={t("ego")} initial={ego} />
      <PersonPicker spaceId={spaceId} name="a" label={t("alter")} initial={alter} />
      <button type="submit" className="fh-button self-start">
        {t("submit")}
      </button>
    </form>
  );
}
