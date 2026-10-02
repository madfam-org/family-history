import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";

const SENSITIVITIES = ["religion", "health", "genetic", "ethnicity", "sexual", "political"] as const;
type SensitivityKey = (typeof SENSITIVITIES)[number];

function isSensitivity(value: string | null | undefined): value is SensitivityKey {
  return (SENSITIVITIES as readonly string[]).includes(value ?? "");
}

/** «Persona viva — solo la ve tu familia», with the rule spelled out underneath. */
export async function PrivatePersonBadge({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "family.privacy" });
  return (
    <div className="flex flex-col gap-1">
      <p className="inline-flex w-fit items-center gap-2 rounded-full border-2 border-accent px-3 py-1 text-sm font-semibold text-accent">
        <svg aria-hidden="true" viewBox="0 0 16 16" className="size-4 fill-current">
          <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1h-.5V4.5A3.5 3.5 0 0 0 8 1Zm-2 5V4.5a2 2 0 1 1 4 0V6H6Z" />
        </svg>
        {t("privateBadge")}
      </p>
      <p className="text-sm text-muted">{t("privateHelp")}</p>
    </div>
  );
}

/** A marker on a sensitive fact (religion, health…), with its class named in the tooltip text. */
export async function SensitiveMarker({ locale, sensitivity }: { locale: Locale; sensitivity: string | null | undefined }) {
  if (!isSensitivity(sensitivity)) return null;
  const t = await getTranslations({ locale, namespace: "family.privacy" });
  const kind = t(`sensitivity.${sensitivity}`);
  return (
    <details className="text-sm">
      <summary className="inline-flex min-h-11 cursor-pointer items-center gap-1 font-semibold text-bark">
        <span aria-hidden="true">◆</span> {t("sensitive")} · {kind}
      </summary>
      <p className="mt-1 text-muted">{t("sensitiveHelp", { kind })}</p>
    </details>
  );
}
