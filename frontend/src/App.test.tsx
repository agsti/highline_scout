import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider, useI18n } from "./lib/i18n";

const apiMocks = vi.hoisted(() => ({
  fetchRegions: vi.fn(),
}));

vi.mock("./lib/api", () => ({
  fetchRegions: apiMocks.fetchRegions,
}));

vi.mock("./components/map/MapView", () => ({
  MapView: ({ region }: { region: string }) => <div data-testid="map-view">{region}</div>,
}));

vi.mock("./components/AppShell", () => ({
  AppShell: ({ sidebar, mobileControls, map }: { sidebar: ReactNode; mobileControls: ReactNode; map: ReactNode }) => (
    <div>
      <div>{sidebar}</div>
      <div>{mobileControls}</div>
      <div>{map}</div>
    </div>
  ),
}));

vi.mock("./components/DesktopSidebar", () => ({
  DesktopSidebar: ({ filters }: { filters: ReactNode }) => <div>{filters}</div>,
}));

vi.mock("./components/MobileControlSheet", () => ({
  MobileControlSheet: ({ filters }: { filters: ReactNode }) => <div>{filters}</div>,
}));

vi.mock("./components/RestrictionLayerControls", () => ({
  RestrictionLayerControls: () => <div>restrictions</div>,
}));

vi.mock("./components/SafetyDisclaimerDialog", () => ({
  SafetyDisclaimerDialog: () => null,
}));

vi.mock("./components/StatusLine", () => ({
  StatusLine: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("./components/ui/button", () => ({
  Button: ({ children }: { children: ReactNode }) => <button type="button">{children}</button>,
}));

vi.mock("./components/FilterControls", () => ({
  FilterControls: ({
    region,
    regions,
    onRegionChange,
  }: {
    region: string;
    regions: Array<{ name: string }>;
    onRegionChange: (value: string) => void;
  }) => (
    <div>
      <div data-testid="current-region">{region}</div>
      <button type="button" onClick={() => onRegionChange(regions[1]?.name ?? "")}>
        change region
      </button>
    </div>
  ),
}));

function LanguageControl() {
  const { setLang } = useI18n();
  return (
    <button type="button" onClick={() => setLang("en")}>
      set english
    </button>
  );
}

function renderApp() {
  return render(
    <I18nProvider>
      <LanguageControl />
      <App />
    </I18nProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    apiMocks.fetchRegions.mockReset().mockResolvedValue([
      { name: "alpha", bounds_lonlat: [1, 2, 3, 4] },
      { name: "beta", bounds_lonlat: [5, 6, 7, 8] },
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads regions once and does not refetch on region or language changes", async () => {
    const user = userEvent.setup();
    renderApp();

    await screen.findAllByTestId("current-region");
    expect(apiMocks.fetchRegions).toHaveBeenCalledTimes(1);
    expect(screen.getAllByTestId("current-region")[0]).toHaveTextContent("alpha");

    await user.click(screen.getAllByRole("button", { name: "change region" })[0]);
    expect(screen.getAllByTestId("current-region")[0]).toHaveTextContent("beta");
    expect(apiMocks.fetchRegions).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "set english" }));
    expect(apiMocks.fetchRegions).toHaveBeenCalledTimes(1);
  });
});
