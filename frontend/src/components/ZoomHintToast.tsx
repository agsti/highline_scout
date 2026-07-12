import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";

export const ZOOM_HINT_MS = 4000;

export function ZoomHintToast({ active }: { active: boolean }) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!active) {
      setVisible(false);
      return;
    }
    setVisible(true);
    const timeout = window.setTimeout(() => setVisible(false), ZOOM_HINT_MS);
    return () => window.clearTimeout(timeout);
  }, [active]);

  if (!visible) return null;

  return (
    <div
      role="status"
      className="pointer-events-none absolute left-1/2 top-[78px] z-[1000] -translate-x-1/2 whitespace-nowrap rounded-full bg-ink/85 px-[13px] py-1.5 text-[11px] font-semibold text-primary-foreground md:hidden"
    >
      {t("densityHint")}
    </div>
  );
}
