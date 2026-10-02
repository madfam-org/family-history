import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/locales";
import { brand, brandEndorsement, brandName } from "@/lib/brand";

export async function SiteFooter({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "landing.footer" });
  const common = await getTranslations({ locale, namespace: "common" });
  return (
    <footer className="mt-16 border-t border-line bg-amate text-bark">
      <div className="fh-container flex flex-col gap-4 py-8 text-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-serif text-base font-bold">{brandName(locale)}</p>
          <p>
            <a href={brand.organization.url} className="text-bark underline">
              {brandEndorsement(locale)}
            </a>
          </p>
        </div>
        <nav aria-label={common("footerNav")}>
          <ul className="flex flex-wrap gap-x-6 gap-y-2">
            <li>
              <a href={`/${locale}/aviso-de-privacidad`} className="text-bark underline">
                {t("aviso")}
              </a>
            </li>
            <li>
              <a href="https://www.gnu.org/licenses/agpl-3.0.html" className="text-bark underline">
                {t("license")}
              </a>
            </li>
            <li>
              <a href={brand.sourceCodeUrl} className="text-bark underline">
                {t("source")}
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
