import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { brandName } from "@/lib/brand";
import { alternateLocaleHref } from "@/lib/i18n/request-context";

import { LanguageSwitch } from "../ui/LanguageSwitch";
import { SkipLink } from "../ui/SkipLink";

export async function SiteHeader({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "landing.nav" });
  const common = await getTranslations({ locale, namespace: "common" });
  const alternate = await alternateLocaleHref(locale);
  const links = [
    { href: "#como-funciona", label: t("how") },
    { href: "#familias-mexicanas", label: t("mexican") },
    { href: "#privacidad", label: t("privacy") },
    { href: "#preguntas", label: t("faq") },
  ];
  return (
    <header className="border-b border-line">
      <SkipLink label={common("skipToContent")} />
      <div className="fh-container flex min-h-16 items-center justify-between gap-4">
        <a href={`/${locale}`} className="font-serif text-xl font-bold text-accent no-underline">
          {brandName(locale)}
        </a>
        <nav aria-label={common("mainNav")} className="hidden md:block">
          <ul className="flex gap-6 text-sm">
            {links.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="text-fg no-underline hover:underline">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <LanguageSwitch
          href={alternate.href}
          targetLocale={alternate.locale}
          label={common("switchLanguage")}
          description={common("switchLanguageLabel")}
        />
      </div>
    </header>
  );
}
