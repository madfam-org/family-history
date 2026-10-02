import { getLocale, getTranslations } from "next-intl/server";

export default async function LocaleNotFound() {
  const locale = await getLocale();
  const t = await getTranslations({ locale, namespace: "notFound" });
  const common = await getTranslations({ locale, namespace: "common" });
  return (
    <main id="contenido" className="fh-container flex min-h-[60vh] flex-col justify-center gap-3 py-12">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p className="text-muted">{t("body")}</p>
      <p>
        <a href={`/${locale}`}>{common("backHome")}</a>
      </p>
    </main>
  );
}
