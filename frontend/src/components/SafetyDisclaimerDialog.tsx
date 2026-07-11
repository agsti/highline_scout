import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface SafetyDisclaimerDialogProps {
  open: boolean;
  onAccept: () => void;
}

export function SafetyDisclaimerDialog({ open, onAccept }: SafetyDisclaimerDialogProps) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[1200] bg-black/40">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="safety-disclaimer-title"
        className="fixed left-1/2 top-1/2 z-[1210] grid w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border bg-background p-6 shadow-lg"
      >
        <div className="flex justify-end">
          <LanguageSwitcher compact />
        </div>
        <div className="space-y-4 text-left">
          <h2 id="safety-disclaimer-title" className="text-lg font-semibold leading-none tracking-tight">
            {t("disclaimerTitle")}
          </h2>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
            <p>{t("disclaimerBody")}</p>
            <p>{t("disclaimerResponsibility")}</p>
            <p className="text-xs">{t("disclaimerPrivacy")}</p>
          </div>
        </div>
        <Button type="button" onClick={onAccept} autoFocus>
          {t("disclaimerAccept")}
        </Button>
      </div>
    </div>
  );
}
