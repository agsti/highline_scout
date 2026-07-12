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

interface LanguageSwitcherProps {
  // "pill" is the standalone nav/dialog treatment; "segmented" is the track
  // that sits in the nav menu's language footer.
  variant?: "pill" | "segmented";
}

export function LanguageSwitcher({ variant = "pill" }: LanguageSwitcherProps) {
  const { lang, setLang, t } = useI18n();
  const segmented = variant === "segmented";

  return (
    <div
      role="group"
      aria-label={t("language")}
      className={cn(
        "flex items-center gap-0.5",
        segmented ? "rounded-[8px] bg-accent p-0.5" : "pr-1",
      )}
    >
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
              "transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              segmented
                ? "rounded-[6px] px-2 py-1 text-[11px]"
                : "rounded-full px-[9px] py-[7px] text-[11px] md:px-[11px] md:py-2 md:text-xs",
              active && segmented && "bg-card font-bold text-primary-deep shadow-[0_1px_3px_rgba(22,48,42,0.12)]",
              active && !segmented && "bg-primary font-bold text-primary-foreground",
              !active && "font-semibold text-muted-foreground",
              !active && (segmented ? "hover:bg-card/60" : "hover:bg-accent"),
            )}
          >
            {SHORT[item]}
          </button>
        );
      })}
    </div>
  );
}
