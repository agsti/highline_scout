import { SlidersHorizontal } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface FilterPillProps {
  summary: string;
  onClick: () => void;
}

export function FilterPill({ summary, onClick }: FilterPillProps) {
  const { t } = useI18n();

  return (
    <button
      type="button"
      data-testid="filter-pill"
      aria-label={t("openControls")}
      onClick={onClick}
      className="pointer-events-auto flex min-h-[44px] items-center gap-2.5 whitespace-nowrap rounded-full bg-primary px-5 py-[13px] text-primary-foreground shadow-filter-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden />
      <span className="text-sm font-bold">{t("filters")}</span>
      <span aria-hidden className="h-4 w-px shrink-0 bg-white/25" />
      <span className="text-[13px] font-medium opacity-[0.85]">{summary}</span>
    </button>
  );
}
