import { useI18n } from "@/lib/i18n";

const STAGE_KEYS = ["howItWorksStageFind", "howItWorksStageFilter", "howItWorksStageScout"] as const;

export function HowItWorksPage() {
  const { t } = useI18n();

  // For SEO: semantic, localized copy gives the map-first product crawlable context.
  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12 text-foreground">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold">{t("howItWorksTitle")}</h1>
        <p className="text-lg text-muted-foreground">{t("howItWorksIntro")}</p>
      </header>

      <section aria-labelledby="methodology-heading" className="space-y-3">
        <h2 id="methodology-heading" className="text-xl font-semibold">
          {t("howItWorksMethod")}
        </h2>
        <ol className="list-decimal space-y-2 pl-6">
          {STAGE_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ol>
        <p className="text-muted-foreground">{t("howItWorksData")}</p>
      </section>

      <section aria-labelledby="safety-heading" className="space-y-3">
        <h2 id="safety-heading" className="text-xl font-semibold">
          {t("howItWorksSafety")}
        </h2>
        <p>{t("howItWorksSafetyBody")}</p>
      </section>

      <a href="/" className="underline underline-offset-4">
        {t("howItWorksMapLink")}
      </a>
    </main>
  );
}
