import { Button } from "@/components/ui/button";
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LABELS: Record<Lang, string> = { ca: "CA", es: "ES", en: "EN" };

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();

  return (
    <div className="flex gap-1" role="group" aria-label={t("language")}>
      {LANGS.map((item) => (
        <Button
          key={item}
          type="button"
          size="sm"
          variant={item === lang ? "default" : "outline"}
          className={cn("h-8 px-3 text-xs", item === lang && "shadow-sm")}
          aria-pressed={item === lang}
          onClick={() => setLang(item)}
        >
          {LABELS[item]}
        </Button>
      ))}
    </div>
  );
}
