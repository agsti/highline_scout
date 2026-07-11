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
import { capture } from "./lib/analytics";
import { fetchRestrictionLayers } from "./lib/api";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { RestrictionLayerMeta } from "./types/highliner";

export function App() {
  const { t } = useI18n();
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

  // Analytics hang off the *commit* callbacks only. onValueChange fires per drag
  // frame; binding events there would record one gesture dozens of times.
  const handleMaxLenCommit = useCallback((value: number) => {
    setMaxLen(value);
    capture("filter_changed", { filter: "max_len", value });
  }, []);

  const handleMinExposureCommit = useCallback((value: number) => {
    setMinExposure(value);
    capture("filter_changed", { filter: "min_exposure", value });
  }, []);

  const handleEnabledRestrictionsChange = useCallback((next: string[]) => {
    setEnabledRestrictions((previous) => {
      const before = new Set(previous);
      const after = new Set(next);
      for (const layer of next) {
        if (!before.has(layer)) capture("restriction_layer_toggled", { layer, enabled: true });
      }
      for (const layer of previous) {
        if (!after.has(layer)) capture("restriction_layer_toggled", { layer, enabled: false });
      }
      return next;
    });
  }, []);

  const filters = (
    <FilterControls
      maxLen={maxLen}
      minExposure={minExposure}
      showAnchors={showAnchors}
      onMaxLenChange={setMaxLen}
      onMaxLenCommit={handleMaxLenCommit}
      onMinExposureChange={setMinExposure}
      onMinExposureCommit={handleMinExposureCommit}
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
      onEnabledChange={handleEnabledRestrictionsChange}
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
            summary={summary}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
          />
        }
        map={
          <MapView
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
