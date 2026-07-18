import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type L from "leaflet";
import { AboutDialog } from "./components/AboutDialog";
import { FeedbackDialog } from "./components/FeedbackDialog";
import { AppShell } from "./components/AppShell";
import { FilterControls, type LengthRange } from "./components/FilterControls";
import { MapChrome } from "./components/MapChrome";
import { MapView } from "./components/map/MapView";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { RestrictionLegend } from "./components/RestrictionLegend";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { capture } from "./lib/analytics";
import { fetchCountries, fetchRestrictionLayers } from "./lib/api";
import {
  clearSavedCountry,
  detectCountry,
  readSavedCountry,
  saveCountry,
} from "./lib/countrySelection";
import { bboxLonLatParam } from "./lib/geo";
import { useI18n } from "./lib/i18n";
import type { CountryEntry, RestrictionAreaMode, RestrictionLayerMeta } from "./types/highliner";

const DEFAULT_LENGTH_RANGE: LengthRange = [20, 150];
const DEFAULT_MIN_EXPOSURE = 30;

function isRestrictionAreaMode(value: string | null): value is RestrictionAreaMode {
  return value === "informative" || value === "exclude";
}

function pickInitialRestrictionAreaMode(): RestrictionAreaMode {
  try {
    const saved = window.localStorage.getItem("restrictionAreaMode");
    if (isRestrictionAreaMode(saved)) return saved;
  } catch {
    // Storage can be unavailable in private mode.
  }
  return "exclude";
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
  const [countries, setCountries] = useState<CountryEntry[]>([]);
  const [country, setCountry] = useState("spain");
  const manualCountryRef = useRef(false);
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [restrictionAreaMode, setRestrictionAreaMode] = useState<RestrictionAreaMode>(
    pickInitialRestrictionAreaMode,
  );
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
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
    fetchRestrictionLayers(country, controller.signal)
      .then((layers) => {
        setRestrictionLayers(layers);
        setEnabledRestrictions(layers.map((layer) => layer.id));
      })
      .catch((error) => {
        if (error.name !== "AbortError") handleError(tRef.current("error", { detail: error.detail ?? String(error) }));
      });
    return () => controller.abort();
  }, [country, handleError]);

  useEffect(() => {
    const catalogController = new AbortController();
    let detectionController: AbortController | undefined;
    let detectionTimeout: number | undefined;

    fetchCountries(catalogController.signal)
      .then(async (available) => {
        setCountries(available);
        const saved = readSavedCountry(available);
        if (saved) {
          setCountry(saved);
          return;
        }
        clearSavedCountry();
        detectionController = new AbortController();
        detectionTimeout = window.setTimeout(() => detectionController?.abort(), 2_000);
        const detected = await detectCountry(available, detectionController.signal);
        if (detected && !manualCountryRef.current) setCountry(detected);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          handleError(tRef.current("error", { detail: String(error) }));
        }
      })
      .finally(() => {
        if (detectionTimeout !== undefined) window.clearTimeout(detectionTimeout);
      });

    return () => {
      catalogController.abort();
      detectionController?.abort();
      if (detectionTimeout !== undefined) window.clearTimeout(detectionTimeout);
    };
  }, [handleError]);

  const handleCountryChange = useCallback((next: string) => {
    manualCountryRef.current = true;
    saveCountry(next);
    setCountry(next);
    setEnabledRestrictions([]);
    setRestrictionLayers([]);
  }, []);
  const countryBounds = countries.find((entry) => entry.id === country)?.bounds_lonlat;

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
            country={country}
            countryBounds={countryBounds}
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
            countries={countries}
            country={country}
            onCountryChange={handleCountryChange}
            onFeedback={() => setFeedbackOpen(true)}
            restrictionAreaMode={restrictionAreaMode}
            onRestrictionAreaModeChange={handleRestrictionAreaModeChange}
            onErrorDismiss={(eventId) =>
              setError((current) => (current?.id === eventId ? null : current))
            }
          />
        }
      />
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
      <SafetyDisclaimerDialog
        open={disclaimerOpen}
        onAccept={() => setDisclaimerOpen(false)}
        countries={countries}
        country={country}
        onCountryChange={handleCountryChange}
      />
    </>
  );
}
