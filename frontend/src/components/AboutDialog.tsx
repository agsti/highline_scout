import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutDialog({ open, onOpenChange }: AboutDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("about")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>{t("aboutBody")}</p>
          <p className="text-xs">{t("aboutData")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
