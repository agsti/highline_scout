import { useCallback, useEffect, useMemo, useState } from "react";
import type L from "leaflet";
import { AboutDialog } from "./components/AboutDialog";
import { AppShell } from "./components/AppShell";
import { FilterControls, type LengthRange } from "./components/FilterControls";
import { MapChrome } from "./components/MapChrome";
import { MapView } from "./components/map/MapView";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { RestrictionLegend } from "./components/RestrictionLegend";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { StatusLine } from "./components/StatusLine";
import { capture } from "./lib/analytics";
import { fetchRestrictionLayers } from "./lib/api";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { RestrictionLayerMeta } from "./types/highliner";

const DEFAULT_LENGTH_RANGE: LengthRange = [20, 150];
const DEFAULT_MIN_EXPOSURE = 30;

export function App() {
  const { t } = useI18n();
  const [mapStatus, setMapStatus] = useState(() => t("searching"));
  const [mapErrorDetail, setMapErrorDetail] = useState("");
  const [, setViewportBbox] = useState("");
  const [draftLengthRange, setDraftLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [draftMinExposure, setDraftMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
  const [appliedLengthRange, setAppliedLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [appliedMinExposure, setAppliedMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
  const [showAnchors, setShowAnchors] = useState(true);
  const [anchorStatus, setAnchorStatus] = useState("");
  const [restrictionLayers, setRestrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [restrictionStatus, setRestrictionStatus] = useState("");
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [densityMode, setDensityMode] = useState(false);

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

  const canApply =
    draftLengthRange[0] !== appliedLengthRange[0] ||
    draftLengthRange[1] !== appliedLengthRange[1] ||
    draftMinExposure !== appliedMinExposure;

  const handleApply = useCallback(() => {
    setAppliedLengthRange(draftLengthRange);
    setAppliedMinExposure(draftMinExposure);
    setSheetOpen(false);
    capture("filters_applied", {
      min_len: draftLengthRange[0],
      max_len: draftLengthRange[1],
      min_exposure: draftMinExposure,
    });
  }, [draftLengthRange, draftMinExposure]);

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
      lengthRange={draftLengthRange}
      minExposure={draftMinExposure}
      showAnchors={showAnchors}
      canApply={canApply}
      onLengthRangeChange={setDraftLengthRange}
      onMinExposureChange={setDraftMinExposure}
      onShowAnchorsChange={setShowAnchors}
      onApply={handleApply}
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

  const legend = <RestrictionLegend layers={restrictionLayers} enabled={enabledRestrictions} />;

  const summary = useMemo(
    () =>
      t("filterSummary", {
        min: appliedLengthRange[0],
        max: appliedLengthRange[1],
        exp: appliedMinExposure,
      }),
    [t, appliedLengthRange, appliedMinExposure],
  );

  return (
    <>
      <AppShell
        map={
          <MapView
            minLen={appliedLengthRange[0]}
            maxLen={appliedLengthRange[1]}
            minExposure={appliedMinExposure}
            showAnchors={showAnchors}
            enabledRestrictions={enabledRestrictions}
            restrictionLayers={restrictionLayers}
            onViewportChange={handleViewportChange}
            onMapStatus={setMapStatus}
            onAnchorStatus={setAnchorStatus}
            onRestrictionStatus={setRestrictionStatus}
            onDensityModeChange={setDensityMode}
          />
        }
        chrome={
          <MapChrome
            summary={summary}
            caveat={t("caveat")}
            legend={legend}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            densityMode={densityMode}
            sheetOpen={sheetOpen}
            onSheetOpenChange={setSheetOpen}
            onAbout={() => setAboutOpen(true)}
          />
        }
      />
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
