import { afterEach, describe, expect, it, vi } from "vitest";
import {
  COUNTRY_STORAGE_KEY,
  clearSavedCountry,
  detectCountry,
  readSavedCountry,
  saveCountry,
} from "./countrySelection";
import type { CountryEntry } from "../types/highliner";

const countries: CountryEntry[] = [
  { id: "spain", country_code: "ES", bounds_lonlat: [-9, 36, 4, 44] },
  { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
  { id: "manual_only", bounds_lonlat: [0, 0, 1, 1] },
];

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("saved country preference", () => {
  it("returns an available saved preference", () => {
    window.localStorage.setItem(COUNTRY_STORAGE_KEY, "france");

    expect(readSavedCountry(countries)).toBe("france");
  });

  it("returns null for a no-longer-available saved preference", () => {
    window.localStorage.setItem(COUNTRY_STORAGE_KEY, "removed_country");

    expect(readSavedCountry(countries)).toBeNull();
  });

  it("writes local storage only when saving a country", () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", {
      clear: vi.fn(),
      getItem: vi.fn(() => null),
      key: vi.fn(() => null),
      length: 0,
      removeItem: vi.fn(),
      setItem,
    } satisfies Storage);

    readSavedCountry(countries);
    clearSavedCountry();
    expect(setItem).not.toHaveBeenCalled();

    saveCountry("spain");
    expect(setItem).toHaveBeenCalledOnce();
    expect(setItem).toHaveBeenCalledWith(COUNTRY_STORAGE_KEY, "spain");
  });
});

describe("detectCountry", () => {
  it("matches IPWho's country_code without persisting it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, country_code: "FR" }),
      }),
    );

    await expect(detectCountry(countries)).resolves.toBe("france");
    expect(window.localStorage.getItem(COUNTRY_STORAGE_KEY)).toBeNull();
    expect(fetch).toHaveBeenCalledWith("https://ipwho.is/", {
      signal: undefined,
    });
  });

  it.each([
    [{ success: false }, "provider failure"],
    [{ success: true, country_code: "XX" }, "unsupported country"],
    [{ success: true, country_code: "fr" }, "malformed code"],
  ])("returns null for %s", async (body, _description) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => body }),
    );

    await expect(detectCountry(countries)).resolves.toBeNull();
  });

  it("returns null when the request rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("CORS")));

    await expect(detectCountry(countries)).resolves.toBeNull();
  });
});
