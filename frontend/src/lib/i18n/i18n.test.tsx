import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { I18nProvider, LANGS, STRINGS, restrictionText, useI18n } from "./index";

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
    expect(result.current.t("searching")).toBe("searching...");
  });
});

describe("restrictionText", () => {
  const fallback = {
    label: "PEIN",
    tooltip: "Text en catala",
    highlight: "catala",
  };

  it("uses Catalan backend fallback for ca", () => {
    expect(restrictionText("pein", "ca", fallback)).toEqual(fallback);
  });

  it("uses frontend translation for en", () => {
    const text = restrictionText("pein", "en", fallback);
    expect(text.label).toBe("PEIN");
    expect(text.tooltip).toContain("Catalonia");
    expect(text.tooltip).toContain(text.highlight);
  });

  it("falls back to backend text for unknown layers", () => {
    expect(restrictionText("unknown", "en", fallback)).toEqual(fallback);
  });
});
