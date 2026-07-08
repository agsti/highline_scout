import { useMemo, useState } from "react";
import { AppShell } from "./components/AppShell";
import { DesktopSidebar } from "./components/DesktopSidebar";
import { FilterControls } from "./components/FilterControls";
import { MobileControlSheet } from "./components/MobileControlSheet";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { StatusLine } from "./components/StatusLine";
import { Button } from "./components/ui/button";
import { useI18n } from "./lib/i18n";
import type { Region, RestrictionLayerMeta } from "./types/highliner";

export function App() {
  const { t } = useI18n();
  const [regions] = useState<Region[]>([]);
  const [region, setRegion] = useState("");
  const [maxLen, setMaxLen] = useState(150);
  const [minExposure, setMinExposure] = useState(30);
  const [showAnchors, setShowAnchors] = useState(true);
  const [restrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);

  const filters = (
    <FilterControls
      regions={regions}
      region={region}
      maxLen={maxLen}
      minExposure={minExposure}
      showAnchors={showAnchors}
      onRegionChange={setRegion}
      onMaxLenChange={setMaxLen}
      onMaxLenCommit={setMaxLen}
      onMinExposureChange={setMinExposure}
      onMinExposureCommit={setMinExposure}
      onShowAnchorsChange={setShowAnchors}
    />
  );

  const statuses = (
    <div className="space-y-1">
      <StatusLine>{t("zoomInToSee", { noun: t("nounZones") })}</StatusLine>
    </div>
  );

  const restrictions = (
    <RestrictionLayerControls
      layers={restrictionLayers}
      enabled={enabledRestrictions}
      onEnabledChange={setEnabledRestrictions}
    />
  );

  const summary = useMemo(
    () => `${t("maxLength")} ${maxLen} m - ${t("minExposure")} ${minExposure} m`,
    [t, maxLen, minExposure],
  );

  return (
    <>
      <AppShell
        sidebar={
          <DesktopSidebar
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
          />
        }
        mobileControls={
          <MobileControlSheet
            region={region}
            summary={summary}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
            actions={<Button variant="outline">{t("mapActions")}</Button>}
          />
        }
        map={
          <div className="flex h-full items-center justify-center bg-secondary text-sm text-muted-foreground">
            Map loading
          </div>
        }
      />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
