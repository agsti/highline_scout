import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchRegions, fetchZones } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("fetches regions and unwraps the response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ regions: [{ name: "cat", bounds_lonlat: [1, 2, 3, 4] }] }),
      }),
    );

    await expect(fetchRegions()).resolves.toEqual([{ name: "cat", bounds_lonlat: [1, 2, 3, 4] }]);
    expect(fetch).toHaveBeenCalledWith("/regions", { signal: undefined });
  });

  it("serializes zone query params", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ type: "FeatureCollection", features: [] }),
      }),
    );

    await fetchZones({
      region: "catalonia",
      bboxLonLat: "1,2,3,4",
      maxLen: 150,
      minExposure: 30,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/zones?region=catalonia&bbox_lonlat=1%2C2%2C3%2C4&max_len=150&min_exposure=30",
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

    await expect(fetchRegions()).rejects.toMatchObject(new ApiError(413, "too many"));
  });
});
