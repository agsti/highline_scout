import { Minus, Plus } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
}

const BUTTON =
  "flex h-[38px] w-[38px] items-center justify-center text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:h-9 md:w-9";

export function ZoomControls({ onZoomIn, onZoomOut }: ZoomControlsProps) {
  const { t } = useI18n();

  return (
    <div className="absolute left-3 top-[78px] z-[1000] flex flex-col overflow-hidden rounded-[10px] bg-card shadow-zoom md:bottom-10 md:left-auto md:right-4 md:top-auto">
      <button type="button" aria-label={t("zoomIn")} onClick={onZoomIn} className={BUTTON}>
        <Plus className="h-4 w-4" aria-hidden />
      </button>
      <span aria-hidden className="h-px bg-hairline" />
      <button type="button" aria-label={t("zoomOut")} onClick={onZoomOut} className={BUTTON}>
        <Minus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
