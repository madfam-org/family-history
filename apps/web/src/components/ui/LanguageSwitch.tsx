import { htmlLang, type Locale } from "@/i18n/locales";

export function LanguageSwitch({
  href,
  targetLocale,
  label,
  description,
}: {
  href: string;
  targetLocale: Locale;
  label: string;
  description: string;
}) {
  return (
    <a
      href={href}
      hrefLang={htmlLang[targetLocale]}
      lang={htmlLang[targetLocale]}
      aria-label={description}
      className="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-semibold text-fg underline-offset-4 hover:underline"
    >
      {label}
    </a>
  );
}
