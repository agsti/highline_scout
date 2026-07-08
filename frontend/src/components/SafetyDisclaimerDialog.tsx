import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface SafetyDisclaimerDialogProps {
  open: boolean;
  onAccept: () => void;
}

export function SafetyDisclaimerDialog({ open, onAccept }: SafetyDisclaimerDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open}>
      <DialogContent hideClose closeLabel={t("closeControls")} className="sm:max-w-md">
        <div className="flex justify-end">
          <LanguageSwitcher compact />
        </div>
        <DialogHeader>
          <DialogTitle>{t("disclaimerTitle")}</DialogTitle>
          <DialogDescription className="space-y-3 text-left">
            <span className="block font-semibold text-destructive">{t("disclaimerLead")}</span>
            <span className="block">{t("disclaimerBody")}</span>
            <span className="block">{t("disclaimerResponsibility")}</span>
          </DialogDescription>
        </DialogHeader>
        <Button type="button" onClick={onAccept} autoFocus>
          {t("disclaimerAccept")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
