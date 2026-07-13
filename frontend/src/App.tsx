import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type L from "leaflet";
import { AboutDialog } from "./components/AboutDialog";
import { AppShell } from "./components/AppShell";
import { FilterControls, type LengthRange } from "./components/FilterControls";
import { MapChrome } from "./components/MapChrome";
import { MapView } from "./components/map/MapView";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { RestrictionLegend } from "./components/RestrictionLegend";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { capture } from "./lib/analytics";
import { fetchRestrictionLayers } from "./lib/api";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { RestrictionAreaMode, RestrictionLayerMeta } from "./types/highliner";

const DEFAULT_LENGTH_RANGE: LengthRange = [20, 150];
const DEFAULT_MIN_EXPOSURE = 30;

function isRestrictionAreaMode(value: string | null): value is RestrictionAreaMode {
  return (
    value === "informative" || value === "exclude-overlaps" || value === "exclude-inside"
  );
}

function pickInitialRestrictionAreaMode(): RestrictionAreaMode {
  try {
    const saved = window.localStorage.getItem("restrictionAreaMode");
    if (isRestrictionAreaMode(saved)) return saved;
  } catch {
    // Storage can be unavailable in private mode.
  }
  return "informative";
}

export function App() {
  const { t } = useI18n();
  const tRef = useRef(t);
  const [error, setError] = useState<{ id: number; message: string } | null>(null);
  const [, setViewportBbox] = useState("");
  const [draftLengthRange, setDraftLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [draftMinExposure, setDraftMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
  const [appliedLengthRange, setAppliedLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [appliedMinExposure, setAppliedMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
  const [showAnchors, setShowAnchors] = useState(false);
  const [restrictionLayers, setRestrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [restrictionAreaMode, setRestrictionAreaMode] = useState<RestrictionAreaMode>(
    pickInitialRestrictionAreaMode,
  );
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [densityMode, setDensityMode] = useState(false);

  const handleError = useCallback((message: string) => {
    setError((previous) => ({ id: (previous?.id ?? 0) + 1, message }));
  }, []);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    const controller = new AbortController();
    fetchRestrictionLayers(controller.signal)
      .then(setRestrictionLayers)
      .catch((error) => {
        if (error.name !== "AbortError") handleError(tRef.current("error", { detail: error.detail ?? String(error) }));
      });
    return () => controller.abort();
  }, [handleError]);

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

  const handleRestrictionAreaModeChange = useCallback((mode: RestrictionAreaMode) => {
    setRestrictionAreaMode(mode);
    try {
      window.localStorage.setItem("restrictionAreaMode", mode);
    } catch {
      // Ignore unavailable storage.
    }
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
            restrictionAreaMode={restrictionAreaMode}
            enabledRestrictions={enabledRestrictions}
            restrictionLayers={restrictionLayers}
            onViewportChange={handleViewportChange}
            onError={handleError}
            onDensityModeChange={setDensityMode}
          />
        }
        chrome={
          <MapChrome
            summary={summary}
            caveat={t("caveat")}
            legend={legend}
            filters={filters}
            restrictions={restrictions}
            errorMessage={error?.message ?? ""}
            errorEventId={error?.id ?? 0}
            densityMode={densityMode}
            sheetOpen={sheetOpen}
            onSheetOpenChange={setSheetOpen}
            onAbout={() => setAboutOpen(true)}
            restrictionAreaMode={restrictionAreaMode}
            onRestrictionAreaModeChange={handleRestrictionAreaModeChange}
            onErrorDismiss={(eventId) =>
              setError((current) => (current?.id === eventId ? null : current))
            }
          />
        }
      />
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
