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
import { fetchRegions, fetchRestrictionLayers } from "./lib/api";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { Region, RestrictionLayerMeta } from "./types/highliner";

export function App() {
  const { t } = useI18n();
  const [regions, setRegions] = useState<Region[]>([]);
  const [region, setRegion] = useState("");
  const [mapStatus, setMapStatus] = useState(() => t("searching"));
  const [mapErrorDetail, setMapErrorDetail] = useState("");
  const [, setViewportBbox] = useState("");
  const [maxLen, setMaxLen] = useState(150);
  const [minExposure, setMinExposure] = useState(30);
  const [showAnchors, setShowAnchors] = useState(true);
  const [anchorStatus, setAnchorStatus] = useState("");
  const [restrictionLayers, setRestrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [restrictionStatus, setRestrictionStatus] = useState("");
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchRegions(controller.signal)
      .then((items) => {
        setRegions(items);
        setRegion((current) => current || items[0]?.name || "");
      })
      .catch((error) => {
        if (error.name !== "AbortError") setMapErrorDetail(error.detail ?? String(error));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchRestrictionLayers(controller.signal)
      .then(setRestrictionLayers)
      .catch((error) => {
        if (error.name !== "AbortError") setRestrictionStatus(t("error", { detail: error.detail ?? String(error) }));
      });
    return () => controller.abort();
  }, [t]);

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
      <StatusLine>{mapErrorDetail ? t("error", { detail: mapErrorDetail }) : mapStatus}</StatusLine>
      {anchorStatus ? <StatusLine>{anchorStatus}</StatusLine> : null}
      {restrictionStatus ? <StatusLine>{restrictionStatus}</StatusLine> : null}
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
          />
        }
        map={
          <MapView
            regions={regions}
            region={region}
            maxLen={maxLen}
            minExposure={minExposure}
            showAnchors={showAnchors}
            enabledRestrictions={enabledRestrictions}
            restrictionLayers={restrictionLayers}
            onViewportChange={handleViewportChange}
            onMapStatus={setMapStatus}
            onAnchorStatus={setAnchorStatus}
            onRestrictionStatus={setRestrictionStatus}
          />
        }
      />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
