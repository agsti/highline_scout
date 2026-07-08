import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { I18nProvider, LANGS, RESTRICTION_STRINGS, STRINGS, restrictionText, useI18n } from "./index";

function wrapper({ children }: { children: ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>;
}

describe("catalog parity", () => {
  it("keeps every language on the Catalan key set", () => {
    const base = Object.keys(STRINGS.ca).sort();
    for (const lang of LANGS) {
      expect(Object.keys(STRINGS[lang]).sort()).toEqual(base);
    }
  });

  it("preserves representative source strings from web/i18n.js", () => {
    expect(STRINGS.ca.region).toBe("Regió");
    expect(STRINGS.ca.searching).toBe("cercant…");
    expect(STRINGS.ca.mapLoading).toBe("Carregant mapa");
    expect(STRINGS.ca.zonePopup).toBe(
      "alçada {min}–{max} m<br>longitud {lmin}–{lmax} m<br>{na} ancoratges · {np} línies",
    );
    expect(STRINGS.ca.anchorSector).toBe("caiguda {a}–{b}° ({drop} m)");

    expect(STRINGS.es.region).toBe("Región");
    expect(STRINGS.es.mapLoading).toBe("Cargando mapa");
    expect(STRINGS.es.hotspotCells).toBe("{n} celdas de puntos de interés (amplía para ver zonas)");
    expect(STRINGS.es.anchorPopup).toBe("anclaje • elev {elev} m<br>{sectors}");

    expect(STRINGS.en.caveat).toBe(
      "Zones to scout — not confirmed-riggable. No bolts, trees, loose rock, access or permissions are verified.",
    );
    expect(STRINGS.en.mapLoading).toBe("Map loading");
    expect(STRINGS.en.densityTooltip).toBe("{n} candidate lines · up to {max} m{lenHint}");
  });
});

describe("useI18n", () => {
  it("interpolates translated strings", () => {
    const { result } = renderHook(() => useI18n(), { wrapper });
    expect(result.current.t("zonesCount", { n: 3 })).toBe("3 zones");
  });

  it("switches language and updates document lang", () => {
    const { result } = renderHook(() => useI18n(), { wrapper });
    act(() => result.current.setLang("en"));
    expect(result.current.lang).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(result.current.t("searching")).toBe("searching…");
  });
});

describe("restrictionText", () => {
  const fallback = {
    label: "PEIN",
    tooltip: "Text en catala",
    highlight: "catala",
  };

  it("keeps every translated restriction highlight as a tooltip substring", () => {
    for (const [lang, entries] of Object.entries(RESTRICTION_STRINGS)) {
      for (const [id, text] of Object.entries(entries ?? {})) {
        expect(text.tooltip).toContain(text.highlight);
        expect(restrictionText(id, lang as (typeof LANGS)[number], fallback)).toEqual(text);
      }
    }
  });

  it("uses Catalan backend fallback for ca", () => {
    expect(restrictionText("pein", "ca", fallback)).toEqual(fallback);
  });

  it("uses frontend translation for en", () => {
    const text = restrictionText("pein", "en", fallback);
    expect(text.label).toBe("PEIN");
    expect(text.tooltip).toContain("Catalonia");
    expect(text.tooltip).toContain(text.highlight);
  });

  it("preserves representative restriction tooltip and highlight source text", () => {
    expect(restrictionText("pein", "es", fallback)).toEqual({
      label: "PEIN",
      tooltip:
        "Plan de Espacios de Interés Natural — el nivel básico de protección en Cataluña (Decreto 328/1992); incluye los espacios de la Red Natura 2000. Régimen urbanístico riguroso; las actividades que puedan lesionar los valores naturales pueden requerir evaluación de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificación de rapaces (aprox. enero-agosto, varía según el espacio).",
      highlight:
        "las actividades que puedan lesionar los valores naturales pueden requerir evaluación de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificación de rapaces (aprox. enero-agosto, varía según el espacio).",
    });

    expect(restrictionText("fauna", "en", fallback)).toEqual({
      label: "Wildlife Reserves",
      tooltip:
        "Wildlife Nature Reserve — protects fauna. Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
      highlight:
        "Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
    });
  });

  it("falls back to backend text for unknown layers", () => {
    expect(restrictionText("unknown", "en", fallback)).toEqual(fallback);
  });
});
