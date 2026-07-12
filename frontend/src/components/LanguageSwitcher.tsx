import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const SHORT: Record<Lang, string> = {
  ca: "CA",
  es: "ES",
  en: "EN",
};
const NAMES: Record<Lang, string> = {
  ca: "Català",
  es: "Español",
  en: "English",
};

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();

  return (
    <div role="group" aria-label={t("language")} className="flex items-center gap-0.5 pr-1">
      {LANGS.map((item) => {
        const active = item === lang;

        return (
          <button
            key={item}
            type="button"
            aria-label={NAMES[item]}
            aria-pressed={active}
            onClick={() => setLang(item)}
            className={cn(
              "rounded-full px-[9px] py-[7px] text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:px-[11px] md:py-2 md:text-xs",
              active
                ? "bg-primary font-bold text-primary-foreground"
                : "font-semibold text-muted-foreground hover:bg-accent",
            )}
          >
            {SHORT[item]}
          </button>
        );
      })}
    </div>
  );
}
