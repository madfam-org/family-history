import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { brandName } from "@/lib/brand";
import { alternateLocaleHref } from "@/lib/i18n/request-context";

import { LanguageSwitch } from "../ui/LanguageSwitch";
import { SkipLink } from "../ui/SkipLink";

export async function AppHeader({ locale, signedIn }: { locale: Locale; signedIn: boolean }) {
  const t = await getTranslations({ locale, namespace: "app.nav" });
  const common = await getTranslations({ locale, namespace: "common" });
  const alternate = await alternateLocaleHref(locale);
  return (
    <header className="border-b border-line bg-surface">
      <SkipLink label={common("skipToContent")} />
      <div className="fh-container flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2">
        <a href={`/${locale}`} className="font-serif text-xl font-bold text-accent no-underline">
          {brandName(locale)}
        </a>
        <div className="flex items-center gap-1">
          {signedIn ? (
            <nav aria-label={common("mainNav")}>
              <ul className="flex items-center gap-1 text-sm">
                <li>
                  <a href={`/${locale}`} className="inline-flex min-h-11 items-center rounded-md px-3 text-fg no-underline hover:underline">
                    {t("families")}
                  </a>
                </li>
                <li>
                  <a
                    href={`/${locale}/ajustes`}
                    className="inline-flex min-h-11 items-center rounded-md px-3 text-fg no-underline hover:underline"
                  >
                    {t("settings")}
                  </a>
                </li>
              </ul>
            </nav>
          ) : null}
          <LanguageSwitch
            href={alternate.href}
            targetLocale={alternate.locale}
            label={common("switchLanguage")}
            description={common("switchLanguageLabel")}
          />
        </div>
      </div>
    </header>
  );
}
