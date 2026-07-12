import type { ReactNode } from "react";
import { CaveatChip } from "./CaveatChip";
import { FilterPill } from "./FilterPill";
import { FiltersPanel } from "./FiltersPanel";
import { FloatingNav } from "./FloatingNav";
import { LineChanceMeter } from "./LineChanceMeter";
import { MobileControlSheet } from "./MobileControlSheet";
import { ZoomHintToast } from "./ZoomHintToast";

interface MapChromeProps {
  summary: string;
  caveat: string;
  legend: ReactNode;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  densityMode: boolean;
  sheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
  onAbout: () => void;
}

export function MapChrome(props: MapChromeProps) {
  return (
    <>
      <FloatingNav onAbout={props.onAbout} />
      <FiltersPanel
        filters={props.filters}
        restrictions={props.restrictions}
        statuses={props.statuses}
      />
      <CaveatChip />
      <ZoomHintToast active={props.densityMode} />

      {props.densityMode ? (
        <div className="pointer-events-none absolute bottom-3 left-1/2 z-[1000] hidden -translate-x-1/2 md:block">
          <LineChanceMeter />
        </div>
      ) : null}

      {/* 24px bottom inset + 44px pill + 16px gap puts the chip stack at 84px,
          and the meter takes that slot when density mode pushes the legend up. */}
      <div className="pointer-events-none absolute inset-x-3 bottom-6 z-[1000] flex flex-col items-center gap-2 md:hidden">
        {props.legend}
        {props.densityMode ? <LineChanceMeter /> : null}
        <div className="mt-2">
          <FilterPill summary={props.summary} onClick={() => props.onSheetOpenChange(true)} />
        </div>
      </div>

      <MobileControlSheet
        filters={props.filters}
        restrictions={props.restrictions}
        statuses={props.statuses}
        caveat={props.caveat}
        open={props.sheetOpen}
        onOpenChange={props.onSheetOpenChange}
      />
    </>
  );
}
