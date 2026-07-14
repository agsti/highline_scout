import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchAnchors, fetchCountries, fetchDensity, fetchRestrictionLayers, fetchRestrictions, fetchZones } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("serializes zone query params", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ type: "FeatureCollection", features: [] }),
      }),
    );

    await fetchZones({
      bboxLonLat: "1,2,3,4",
      minLen: 20,
      maxLen: 150,
      minExposure: 30,
      country: "france",
    });

    expect(fetch).toHaveBeenCalledWith(
      "/zones?bbox_lonlat=1%2C2%2C3%2C4&min_len=20&max_len=150&min_exposure=30&country=france",
      { signal: undefined },
    );
  });

  it("raises ApiError with backend detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
        json: async () => ({ detail: "too many" }),
      }),
    );

    await expect(
      fetchZones({ bboxLonLat: "1,2,3,4", minLen: 20, maxLen: 150, minExposure: 30, country: "spain" }),
    ).rejects.toMatchObject(new ApiError(413, "too many"));
  });

  it("serializes country for each map resource and unwraps countries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ countries: [], layers: [], type: "FeatureCollection", features: [] }) }));
    await fetchCountries();
    await fetchDensity({ country: "france", z: 8, bboxLonLat: "1,2,3,4" });
    await fetchAnchors({ country: "france", bboxLonLat: "1,2,3,4" });
    await fetchRestrictionLayers("france");
    await fetchRestrictions({ country: "france", bboxLonLat: "1,2,3,4", layers: ["zepa"] });
    expect(fetch).toHaveBeenCalledWith("/countries", { signal: undefined });
    expect(fetch).toHaveBeenCalledWith("/density?z=8&bbox_lonlat=1%2C2%2C3%2C4&country=france", { signal: undefined });
    expect(fetch).toHaveBeenCalledWith("/anchors?bbox_lonlat=1%2C2%2C3%2C4&country=france", { signal: undefined });
    expect(fetch).toHaveBeenCalledWith("/restrictions/layers?country=france", { signal: undefined });
    expect(fetch).toHaveBeenCalledWith("/restrictions?bbox_lonlat=1%2C2%2C3%2C4&layers=zepa&country=france", { signal: undefined });
  });
});
