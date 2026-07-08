import { useI18n } from "./lib/i18n";

export function App() {
  const { t } = useI18n();

  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <h1 className="text-lg font-semibold">Highline Scout</h1>
      <span className="sr-only">{t("language")}</span>
    </main>
  );
}
