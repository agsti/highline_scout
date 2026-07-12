import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

const mapProps = vi.fn();

vi.mock("./lib/analytics", () => ({
  capture: vi.fn(),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: vi.fn().mockResolvedValue([]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: (props: Record<string, unknown>) => {
    mapProps(props);
    return <div data-testid="map" />;
  },
}));

function lastMapProps() {
  return mapProps.mock.calls.at(-1)?.[0] as {
    minLen: number;
    maxLen: number;
    minExposure: number;
    showAnchors: boolean;
  };
}

beforeEach(() => {
  mapProps.mockClear();
});

const applyButton = () => screen.getByRole("button", { name: /apply filters/i });

describe("App filter application", () => {
  it("keeps the map on the applied filters while the slider is moved", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(lastMapProps().minLen).toBe(20);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    expect(lastMapProps().minLen).toBe(20);
  });

  it("pushes the draft to the map only when Apply is pressed", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    await user.click(applyButton());

    expect(lastMapProps().minLen).toBe(21);
  });

  it("disables Apply until the draft diverges, and again once applied", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(applyButton()).toBeDisabled();

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    expect(applyButton()).toBeEnabled();

    await user.click(applyButton());
    expect(applyButton()).toBeDisabled();
  });

  it("sends the anchors toggle straight to the map without an Apply", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(lastMapProps().showAnchors).toBe(false);
    await user.click(screen.getByRole("checkbox", { name: /show anchors/i }));

    expect(lastMapProps().showAnchors).toBe(true);
    expect(applyButton()).toBeDisabled();
  });
});
