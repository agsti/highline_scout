import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

interface SafetyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SafetyDialog({ open, onOpenChange }: SafetyDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("safety")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
          <p>{t("disclaimerBody")}</p>
          <p>{t("disclaimerResponsibility")}</p>
          <p>{t("caveat")}</p>
          <p className="text-xs">{t("restrictionCredit")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
