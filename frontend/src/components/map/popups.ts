import type { DensityProperties, ZoneProperties } from "@/types/highliner";
import type { StringKey } from "@/lib/i18n";

type T = (key: StringKey, params?: Record<string, string | number>) => string;

export function zonePopupHtml(p: ZoneProperties, t: T): string {
  return t("zonePopup", {
    min: p.height_min,
    max: p.height_max,
    lmin: Math.round(p.length_min),
    lmax: Math.round(p.length_max),
  });
}

export function densityTooltipHtml(p: DensityProperties, t: T): string {
  const lenHint =
    p.length_min == null || p.length_max == null
      ? ""
      : t("densityLenHint", { min: Math.round(p.length_min), max: Math.round(p.length_max) });
  return t("densityTooltip", { n: p.n_pairs, max: Math.round(p.max_exposure), lenHint });
}
