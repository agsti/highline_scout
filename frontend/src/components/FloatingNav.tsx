import { Info } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { BrandPill } from "./BrandPill";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface FloatingNavProps {
  onAbout: () => void;
}

export function FloatingNav({ onAbout }: FloatingNavProps) {
  const { t } = useI18n();

  return (
    <header className="pointer-events-none absolute inset-x-3 top-3.5 z-[1000] flex items-center justify-between gap-2 md:inset-x-4 md:top-4">
      <div className="pointer-events-auto">
        <BrandPill />
      </div>
      <div className="pointer-events-auto flex items-center gap-0.5 rounded-full bg-card/[0.94] p-1 shadow-pill backdrop-blur-[8px] md:shadow-pill-lg">
        <LanguageSwitcher />
        <span aria-hidden className="h-5 w-px shrink-0 bg-hairline md:h-[22px]" />
        <button
          type="button"
          aria-label={t("about")}
          onClick={onAbout}
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:h-9 md:w-9"
        >
          <Info className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </header>
  );
}
