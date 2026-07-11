import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LABELS: Record<Lang, string> = {
  ca: "Catala",
  es: "Espanol",
  en: "English",
};
const FLAG_LABELS: Record<Lang, string> = {
  ca: "Catalan flag",
  es: "Spanish flag",
  en: "English flag",
};
const FLAG_BACKGROUNDS: Record<Exclude<Lang, "en">, string> = {
  ca: "repeating-linear-gradient(to bottom, #f4c542 0 11.11%, #b72d2d 11.11% 22.22%)",
  es: "linear-gradient(to bottom, #b72d2d 0 25%, #f4c542 25% 75%, #b72d2d 75% 100%)",
};

function LanguageFlag({ item, className }: { item: Lang; className?: string }) {
  const flagClassName = cn(
    "block h-5 w-7 overflow-hidden rounded-[3px] border border-foreground/20 shadow-sm",
    className,
  );

  if (item === "en") {
    return (
      <span
        role="img"
        aria-label={FLAG_LABELS[item]}
        className={flagClassName}
      >
        <svg aria-hidden="true" viewBox="0 0 60 40" className="h-full w-full">
          <g>
            <rect width="60" height="40" fill="#1f3d7a" />
            <path d="M0 0 60 40M60 0 0 40" stroke="#fff" strokeWidth="11" />
            <path d="M0 0 60 40M60 0 0 40" stroke="#c62828" strokeWidth="5" />
            <path d="M30 0v40M0 20h60" stroke="#fff" strokeWidth="15" />
            <path d="M30 0v40M0 20h60" stroke="#c62828" strokeWidth="9" />
          </g>
        </svg>
      </span>
    );
  }

  return (
    <span
      role="img"
      aria-label={FLAG_LABELS[item]}
      className={flagClassName}
      style={{ background: FLAG_BACKGROUNDS[item] }}
    />
  );
}

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();

  return (
    <Select value={lang} onValueChange={(value) => setLang(value as Lang)}>
      <SelectTrigger
        aria-label={t("language")}
        className="h-9 w-12 justify-center rounded-full border-0 bg-background/80 px-0 shadow-sm backdrop-blur transition-colors hover:bg-accent focus:ring-2 [&>svg]:hidden"
      >
        <LanguageFlag item={lang} />
      </SelectTrigger>
      <SelectContent align="end" className="min-w-[9rem]">
        {LANGS.map((item) => (
          <SelectItem key={item} value={item} className="gap-2 pr-8">
            <span className="flex items-center gap-2">
              <LanguageFlag item={item} className="h-4 w-6" />
              <span className="text-sm">{LABELS[item]}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
