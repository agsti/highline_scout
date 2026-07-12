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
    expect(STRINGS.ca.searching).toBe("cercant…");
    expect(STRINGS.ca.mapLoading).toBe("Carregant mapa");
    expect(STRINGS.ca.zonePopup).toBe("alçada {min}–{max} m<br>longitud {lmin}–{lmax} m");

    expect(STRINGS.es.mapLoading).toBe("Cargando mapa");
    expect(STRINGS.es.hotspotCells).toBe("{n} celdas de puntos de interés (amplía para ver zonas)");

    expect(STRINGS.en.caveat).toBe(
      "Zones to scout — not confirmed-riggable. No bolts, trees, loose rock, access or permissions are verified.",
    );
    expect(STRINGS.en.mapLoading).toBe("Map loading");
    expect(STRINGS.en.densityTooltip).toBe("{n} candidate lines · up to {max} m{lenHint}");
  });

  it("discloses cookieless analytics in every language", () => {
    expect(STRINGS.ca.disclaimerPrivacy).toMatch(/sense galetes/i);
    expect(STRINGS.es.disclaimerPrivacy).toMatch(/sin cookies/i);
    expect(STRINGS.en.disclaimerPrivacy).toMatch(/no cookies/i);
  });

  it("carries the floating-chrome copy in every language", () => {
    expect(STRINGS.ca.caveatShort).toBe("Zones sense verificar — valora el terreny tu mateix");
    expect(STRINGS.es.caveatShort).toBe("Zonas sin verificar — valora el terreno tú mismo");
    expect(STRINGS.en.caveatShort).toBe("Unverified zones — assess the terrain yourself");

    expect(STRINGS.es.densityHint).toBe("Amplía para ver zonas");
    expect(STRINGS.en.about).toBe("About Highline Scout");
    expect(STRINGS.ca.zoomIn).toBe("Amplia");
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
    label: "L",
    tooltip: "T",
    highlight: "T",
  };

  it("keeps every translated restriction highlight as a tooltip substring", () => {
    for (const [lang, entries] of Object.entries(RESTRICTION_STRINGS)) {
      for (const [id, text] of Object.entries(entries ?? {})) {
        expect(text.tooltip).toContain(text.highlight);
        expect(restrictionText(id, lang as (typeof LANGS)[number], fallback)).toEqual(text);
      }
    }
  });

  it("falls back to the server text for the base language (en)", () => {
    expect(restrictionText("zepa", "en", fallback)).toEqual(fallback);
  });

  it("returns the Spanish override for a known layer", () => {
    expect(restrictionText("enp", "es", fallback)).toEqual({
      label: "Espacios Naturales Protegidos",
      tooltip:
        "Espacio Natural Protegido — una figura de protección estatal o autonómica como un parque nacional o natural, una reserva natural o un monumento natural, cada uno con su propio plan de gestión. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    });
  });

  it("returns the Catalan override for a known layer", () => {
    expect(restrictionText("zepa", "ca", fallback)).toEqual({
      label: "ZEPA (Aus)",
      tooltip:
        "Zona d'Especial Protecció per a les Aus — Xarxa Natura 2000 (Directiva Aus). Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
      highlight:
        "Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
    });
  });

  it("falls back to backend text for unknown layers", () => {
    expect(restrictionText("unknown", "en", fallback)).toEqual(fallback);
  });
});
