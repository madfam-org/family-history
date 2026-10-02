import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import type { ErrorCode } from "@/lib/api/errors";
import type { CompadrazgoItem } from "@/lib/api/schemas-family";
import { compadrazgoGroup, type CompadrazgoGroup } from "@/lib/forms/family";

const GROUP_ORDER: readonly CompadrazgoGroup[] = ["godparents", "godchildren", "compadres", "other"];

/**
 * Padrinos, ahijados y compadres of one person (addendum D, `GET …/compadrazgo`). Labels come
 * from the API in both languages («madrina de bautizo», «compadre»); the web only groups them.
 */
export async function CompadrazgoPanel({
  locale,
  result,
}: {
  locale: Locale;
  result: { ok: true; items: readonly CompadrazgoItem[] } | { ok: false; code: ErrorCode };
}) {
  const t = await getTranslations({ locale, namespace: "family.compadrazgo" });
  const errors = await getTranslations({ locale, namespace: "errors" });
  const groups = new Map<CompadrazgoGroup, CompadrazgoItem[]>();
  if (result.ok) {
    for (const item of result.items) {
      const group = compadrazgoGroup(item.relation);
      groups.set(group, [...(groups.get(group) ?? []), item]);
    }
  }
  const sacramentLabel = (value: string | null) =>
    value && t.has(`sacraments.${value}` as "sacraments.bautizo") ? t(`sacraments.${value}` as "sacraments.bautizo") : null;

  return (
    <section aria-labelledby="compadrazgo" className="fh-card">
      <h2 id="compadrazgo" className="text-xl font-bold">
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("lead")}</p>
      {!result.ok ? (
        <p role="alert" className="mt-3 font-semibold text-danger">
          {t("unavailable", { error: errors(result.code) })}
        </p>
      ) : result.items.length === 0 ? (
        <p className="mt-3 text-muted">{t("empty")}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          {GROUP_ORDER.filter((group) => groups.has(group)).map((group) => (
            <div key={group}>
              <h3 className="font-semibold">{t(`groups.${group}`)}</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {(groups.get(group) ?? []).map((item, index) => {
                  const sacrament = sacramentLabel(item.sacrament);
                  return (
                    <li key={`${item.person_id}-${item.relation}-${index}`}>
                      <a href={`/${locale}/personas/${encodeURIComponent(item.person_id)}`} className="font-semibold">
                        {item.display_name}
                      </a>
                      <span className="text-muted">
                        {" · "}
                        {locale === "en" ? item.label_en : item.label_es}
                        {sacrament && !(locale === "en" ? item.label_en : item.label_es).includes(sacrament)
                          ? ` ${t("sacrament", { sacrament })}`
                          : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
