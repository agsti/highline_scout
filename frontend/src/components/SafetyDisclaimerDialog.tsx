import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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

  return (
    <Dialog open={open}>
      {/* This is a blocking first-run gate, not a dismissable dialog: it must
          only close via the Accept button, so Escape and outside clicks are
          swallowed here rather than wired to an onOpenChange. */}
      <DialogContent
        hideClose
        closeLabel={t("close")}
        className="z-[1210] max-w-md"
        onEscapeKeyDown={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => event.preventDefault()}
      >
        <div className="flex justify-end">
          <LanguageSwitcher />
        </div>
        <DialogHeader className="text-left">
          <DialogTitle>{t("disclaimerTitle")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
          <p>{t("disclaimerBody")}</p>
          <p>{t("disclaimerResponsibility")}</p>
          <p className="text-xs">{t("disclaimerPrivacy")}</p>
        </div>
        <Button type="button" onClick={onAccept} autoFocus>
          {t("disclaimerAccept")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
