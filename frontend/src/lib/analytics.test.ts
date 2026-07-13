import { beforeEach, describe, expect, it, vi } from "vitest";

const initMock = vi.fn();
const captureMock = vi.fn();
const loadPosthogMock = vi.fn();
const posthog = { init: initMock, capture: captureMock };

vi.mock("posthog-js", () => ({
  default: posthog,
}));

vi.mock("./analytics-loader", () => ({
  loadPosthog: loadPosthogMock,
}));

async function loadModule() {
  return import("./analytics");
}

beforeEach(() => {
  vi.resetModules();
  initMock.mockClear();
  captureMock.mockClear();
  loadPosthogMock.mockReset();
  loadPosthogMock.mockResolvedValue(posthog);
});

describe("shouldEnableAnalytics", () => {
  it("enables on a deployed production host", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    expect(shouldEnableAnalytics(true, "highlinescout.com")).toBe(true);
  });

  it("stays off in a dev build", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    expect(shouldEnableAnalytics(false, "highlinescout.com")).toBe(false);
  });

  it("stays off on local hosts even in a production build", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    for (const host of ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]) {
      expect(shouldEnableAnalytics(true, host)).toBe(false);
    }
  });
});

describe("capture", () => {
  it("no-ops when initAnalytics was never called", async () => {
    const { capture } = await loadModule();
    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("no-ops when init was gated off", async () => {
    const { initAnalytics, capture } = await loadModule();
    await initAnalytics(false, "highlinescout.com");
    capture("zone_opened", { n_pairs: 3 });
    expect(loadPosthogMock).not.toHaveBeenCalled();
    expect(initMock).not.toHaveBeenCalled();
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("does not load PostHog on a local production host", async () => {
    const { initAnalytics } = await loadModule();

    await initAnalytics(true, "localhost");

    expect(loadPosthogMock).not.toHaveBeenCalled();
    expect(initMock).not.toHaveBeenCalled();
  });

  it("loads PostHog only after the production gate passes", async () => {
    const { initAnalytics } = await loadModule();

    await initAnalytics(true, "highlinescout.com");

    expect(initMock).toHaveBeenCalledWith(
      "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst",
      expect.objectContaining({
        persistence: "memory",
        cookieless_mode: "always",
        person_profiles: "identified_only",
        disable_session_recording: true,
        disable_surveys: true,
        disable_product_tours: true,
        disable_conversations: true,
      }),
    );
  });

  it("flushes events captured while PostHog is loading in order", async () => {
    let resolveLoader: (() => void) | undefined;
    loadPosthogMock.mockImplementationOnce(
      () => new Promise((resolve) => { resolveLoader = () => resolve(posthog); }),
    );
    const { capture, initAnalytics } = await loadModule();

    const initializing = initAnalytics(true, "highlinescout.com");
    capture("filter_changed", { min_len: 20 });
    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).not.toHaveBeenCalled();

    resolveLoader?.();
    await initializing;
    expect(captureMock.mock.calls).toEqual([
      ["filter_changed", { min_len: 20 }],
      ["zone_opened", { n_pairs: 3 }],
    ]);
  });

  it("absorbs a loader failure and discards pending events before a retry", async () => {
    loadPosthogMock.mockRejectedValueOnce(new Error("PostHog unavailable"));
    const { capture, initAnalytics } = await loadModule();

    const initializing = initAnalytics(true, "highlinescout.com");
    capture("filter_changed", { min_len: 20 });
    await expect(initializing).resolves.toBeUndefined();

    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).not.toHaveBeenCalled();

    await initAnalytics(true, "highlinescout.com");
    expect(initMock).toHaveBeenCalledTimes(1);
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("forwards events after PostHog loads", async () => {
    const { initAnalytics, capture } = await loadModule();
    await initAnalytics(true, "highlinescout.com");
    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).toHaveBeenCalledWith("zone_opened", { n_pairs: 3 });
  });
});

describe("captureMapSettled", () => {
  it("emits once after the debounce, collapsing a burst of pans", async () => {
    vi.useFakeTimers();
    const { initAnalytics, captureMapSettled, MAP_SETTLED_DEBOUNCE_MS } = await loadModule();
    await initAnalytics(true, "highlinescout.com");

    captureMapSettled(13, 41.6, 1.83);
    captureMapSettled(14, 41.7, 1.84);
    captureMapSettled(15, 41.8, 1.85);
    expect(captureMock).not.toHaveBeenCalled();

    vi.advanceTimersByTime(MAP_SETTLED_DEBOUNCE_MS);
    expect(captureMock).toHaveBeenCalledTimes(1);
    expect(captureMock).toHaveBeenCalledWith("map_settled", {
      zoom: 15,
      lat: 41.8,
      lon: 1.85,
    });
    vi.useRealTimers();
  });
});

describe("cookieless persistence", () => {
  it("stores nothing on the device, so no consent banner is required", async () => {
    const { initAnalytics } = await loadModule();
    await initAnalytics(true, "highlinescout.com");

    const options = initMock.mock.calls[0]?.[1] as Record<string, unknown>;
    // No cookie, no localStorage: distinct_id lives in memory for the page's life.
    expect(options.persistence).toBe("memory");
    // Recovers same-day unique visitors via a server-side daily-rotating hash
    // instead of a device-held distinct_id — still zero device storage.
    expect(options.cookieless_mode).toBe("always");
    // We never call identify(), so no person profiles are created.
    expect(options.person_profiles).toBe("identified_only");
    // Session replay is dashboard-toggleable; pinning it off keeps DOM content
    // (which would need consent) from ever being recorded.
    expect(options.disable_session_recording).toBe(true);
    // Surveys, product tours, and conversations are also dashboard-toggleable
    // and each writes its own raw localStorage key if enabled there.
    expect(options.disable_surveys).toBe(true);
    expect(options.disable_product_tours).toBe(true);
    expect(options.disable_conversations).toBe(true);
  });
});
