import type { ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";

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
        onClick={() => props.onOpenChange(true)}
        className="fixed inset-x-3 bottom-0 z-[1100] cursor-pointer rounded-t-xl border border-b-0 bg-card/95 p-3 pb-4 shadow-xl backdrop-blur"
      >
        <SheetTrigger asChild>
          <button
            type="button"
            aria-label={t("openControls")}
            className="mb-1 flex w-full items-center justify-center rounded-md py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <span className="h-1 w-10 rounded-full bg-border" />
          </button>
        </SheetTrigger>
        <div className="flex items-center gap-2 text-sm font-semibold">
          <SlidersHorizontal className="h-4 w-4 shrink-0" />
          {t("filters")}
        </div>
        <div className="mt-1 text-sm text-muted-foreground">{props.summary}</div>
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
        </div>
      </SheetContent>
    </Sheet>
  );
}
