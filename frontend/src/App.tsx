import { useCallback, useEffect, useMemo, useState } from "react";
import type L from "leaflet";
import { AppShell } from "./components/AppShell";
import { DesktopSidebar } from "./components/DesktopSidebar";
import { FilterControls } from "./components/FilterControls";
import { MobileControlSheet } from "./components/MobileControlSheet";
import { MapView } from "./components/map/MapView";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { StatusLine } from "./components/StatusLine";
import { Button } from "./components/ui/button";
import { fetchRegions } from "./lib/api";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { Region, RestrictionLayerMeta } from "./types/highliner";

export function App() {
  const { t } = useI18n();
  const [regions, setRegions] = useState<Region[]>([]);
  const [region, setRegion] = useState("");
  const [mapStatus, setMapStatus] = useState("");
  const [viewportBbox, setViewportBbox] = useState("");
  const [maxLen, setMaxLen] = useState(150);
  const [minExposure, setMinExposure] = useState(30);
  const [showAnchors, setShowAnchors] = useState(true);
  const [restrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchRegions(controller.signal)
      .then((items) => {
        setRegions(items);
        if (!region && items[0]) setRegion(items[0].name);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setMapStatus(t("error", { detail: error.detail ?? String(error) }));
      });
    return () => controller.abort();
  }, [region, t]);

  const handleViewportChange = useCallback((map: L.Map) => {
    setViewportBbox(bboxLonLatParam(map.getBounds()));
  }, []);

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
      <StatusLine>{mapStatus || (viewportBbox ? "" : t("searching"))}</StatusLine>
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
          <MapView regions={regions} region={region} onViewportChange={handleViewportChange} />
        }
      />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
