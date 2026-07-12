import { TriangleAlert } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function CaveatChip() {
  const { t } = useI18n();

  return (
    <div className="absolute bottom-3 left-4 z-[1000] hidden items-center gap-2 rounded-full bg-card/[0.92] px-3.5 py-1.5 shadow-pill md:flex">
      <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      <span className="text-[11px] font-semibold text-destructive">{t("caveatShort")}</span>
    </div>
  );
}
