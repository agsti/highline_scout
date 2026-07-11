import type { ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface MobileControlSheetProps {
  summary: string;
  legend: ReactNode;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MobileControlSheet(props: MobileControlSheetProps) {
  const { t } = useI18n();
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <div
        data-testid="mobile-summary-card"
        className="fixed inset-x-3 bottom-3 z-[1100] rounded-xl border bg-card/95 p-3 shadow-xl backdrop-blur"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-border" />
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1 text-sm font-medium">{props.summary}</div>
          <SheetTrigger asChild>
            <Button type="button" size="sm" aria-label={t("openControls")}>
              <SlidersHorizontal className="mr-2 h-4 w-4" />
              {t("filters")}
            </Button>
          </SheetTrigger>
        </div>
        {props.legend}
      </div>
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
          {props.statuses}
          {props.restrictions}
          <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
            {props.caveat}
          </p>
          <LanguageSwitcher compact />
        </div>
      </SheetContent>
    </Sheet>
  );
}
