import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  country?: string;
}

export function AboutDialog({ open, onOpenChange, country = "spain" }: AboutDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("about")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>{t("aboutBody")}</p>
          <p className="text-xs">
            {t(country === "switzerland" ? "aboutDataSwitzerland" : "aboutData")}
          </p>
          <p className="text-xs">{t("aboutPrivacy")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
