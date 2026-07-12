import type { ReactNode } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";

interface MobileControlSheetProps {
  filters: ReactNode;
  restrictions: ReactNode;
  caveat: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MobileControlSheet(props: MobileControlSheetProps) {
  const { t } = useI18n();

  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent
        side="bottom"
        closeLabel={t("closeControls")}
        className="max-h-[88dvh] overflow-y-auto rounded-t-2xl"
      >
        <SheetHeader>
          <SheetTitle>{t("filters")}</SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-5">
          {props.filters}
          {props.restrictions}
          <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
            {props.caveat}
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
