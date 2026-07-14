import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

const captureMock = vi.fn();
vi.mock("./lib/analytics", () => ({
  capture: (event: string, properties?: Record<string, unknown>) =>
    captureMock(event, properties),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchCountries: vi.fn().mockResolvedValue([]),
  fetchRestrictionLayers: vi.fn().mockResolvedValue([
    { id: "zepa", label: "ZEPA", tooltip: "", highlight: "", color: "#f00" },
  ]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));

vi.mock("./components/SafetyDisclaimerDialog", () => ({
  SafetyDisclaimerDialog: () => null,
}));

beforeEach(() => {
  captureMock.mockClear();
});

describe("App analytics", () => {
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

  it("emits restriction_layer_toggled when a layer is enabled", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const checkbox = await screen.findByRole("checkbox", { name: /ZEPA/i });
    await user.click(checkbox);

    expect(captureMock).toHaveBeenCalledWith("restriction_layer_toggled", {
      layer: "zepa",
      enabled: true,
    });
  });
});
