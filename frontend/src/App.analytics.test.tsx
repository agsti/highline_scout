import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

const captureMock = vi.fn();
const countryMocks = vi.hoisted(() => ({
  readSavedCountry: vi.fn().mockReturnValue(null),
  saveCountry: vi.fn(),
  clearSavedCountry: vi.fn(),
  detectCountry: vi.fn().mockResolvedValue("france"),
}));
vi.mock("./lib/analytics", () => ({
  capture: (event: string, properties?: Record<string, unknown>) =>
    captureMock(event, properties),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchCountries: vi.fn().mockResolvedValue([
    { id: "france", country_code: "FR", bounds_lonlat: [-5, 42, 8, 51] },
  ]),
  fetchRestrictionLayers: vi.fn().mockResolvedValue([
    { id: "zepa", label: "ZEPA", tooltip: "", highlight: "", color: "#f00" },
  ]),
}));

vi.mock("./lib/countrySelection", () => countryMocks);

vi.mock("./components/map/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));

vi.mock("./components/SafetyDisclaimerDialog", () => ({
  SafetyDisclaimerDialog: () => null,
}));

beforeEach(() => {
  captureMock.mockClear();
  countryMocks.readSavedCountry.mockReset().mockReturnValue(null);
  countryMocks.saveCountry.mockReset();
  countryMocks.clearSavedCountry.mockReset();
  countryMocks.detectCountry.mockReset().mockResolvedValue("france");
});

describe("App analytics", () => {
  it("does not emit country or location analytics for automatic selection", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await vi.waitFor(() => expect(countryMocks.detectCountry).toHaveBeenCalled());

    expect(
      captureMock.mock.calls.some(([, properties]) =>
        Object.keys(properties ?? {}).some((key) => /country|location/i.test(key)),
      ),
    ).toBe(false);
  });

  it("emits nothing while a filter is only being drafted", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    const filterEvents = captureMock.mock.calls.filter(([event]) => event.startsWith("filter"));
    expect(filterEvents).toEqual([]);
  });

  it("emits filters_applied with the applied values when Apply is pressed", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    sliders[1].focus();
    await user.keyboard("{ArrowLeft}");
    await user.click(screen.getByRole("button", { name: /apply filters/i }));

    const applied = captureMock.mock.calls.filter(([event]) => event === "filters_applied");
    expect(applied).toHaveLength(1);
    expect(applied[0][1]).toEqual({ min_len: 21, max_len: 149, min_exposure: 30 });
  });

  it("emits restriction_layer_toggled when a layer is toggled", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    // Layers start enabled, so the first click turns ZEPA off.
    const checkbox = await screen.findByRole("checkbox", { name: /ZEPA/i });
    await user.click(checkbox);

    expect(captureMock).toHaveBeenCalledWith("restriction_layer_toggled", {
      layer: "zepa",
      enabled: false,
    });

    await user.click(checkbox);

    expect(captureMock).toHaveBeenCalledWith("restriction_layer_toggled", {
      layer: "zepa",
      enabled: true,
    });
  });
});
