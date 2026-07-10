import { useEffect, type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider, useI18n } from "./lib/i18n";

const apiMocks = vi.hoisted(() => ({
  fetchRestrictionLayers: vi.fn(),
}));

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: apiMocks.fetchRestrictionLayers,
}));

vi.mock("./components/map/MapView", () => ({
  MapView: ({
    showAnchors,
    enabledRestrictions,
    restrictionLayers,
    onMapStatus,
  }: {
    showAnchors?: boolean;
    enabledRestrictions?: string[];
    restrictionLayers?: Array<{ id: string }>;
    onMapStatus?: (status: string) => void;
  }) => {
    useEffect(() => {
      onMapStatus?.("3 zones");
    }, [onMapStatus]);
    return (
      <div data-testid="map-view">
        <div data-testid="show-anchors">{String(showAnchors)}</div>
        <div data-testid="enabled-restrictions">{enabledRestrictions?.join(",") ?? ""}</div>
        <div data-testid="restriction-layer-count">{restrictionLayers?.length ?? 0}</div>
      </div>
    );
  },
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
  DesktopSidebar: ({ filters, statuses }: { filters: ReactNode; statuses: ReactNode }) => (
    <div>
      {filters}
      {statuses}
    </div>
  ),
}));

vi.mock("./components/MobileControlSheet", () => ({
  MobileControlSheet: ({ filters, statuses, actions }: { filters: ReactNode; statuses: ReactNode; actions?: ReactNode }) => (
    <div>
      {filters}
      {statuses}
      {actions ? <div data-testid="mobile-actions-slot">{actions}</div> : null}
    </div>
  ),
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
  FilterControls: (_props: Record<string, unknown>) => <div data-testid="filter-controls" />,
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
    apiMocks.fetchRestrictionLayers.mockReset().mockResolvedValue([
      {
        id: "zepa",
        label: "ZEPA (Birds)",
        tooltip: "tooltip",
        highlight: "tooltip",
        color: "#0a0",
      },
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the map status in both desktop and mobile status areas", async () => {
    renderApp();

    await screen.findAllByText("3 zones");
    expect(screen.getAllByText("3 zones")).toHaveLength(2);
  });

  it("does not show map actions in the mobile filter controls", async () => {
    renderApp();

    await screen.findAllByTestId("filter-controls");
    expect(screen.queryByTestId("mobile-actions-slot")).not.toBeInTheDocument();
  });

  it("loads restriction layer metadata and passes it into the map", async () => {
    const user = userEvent.setup();
    renderApp();

    await screen.findByTestId("restriction-layer-count");
    expect(apiMocks.fetchRestrictionLayers).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("restriction-layer-count")).toHaveTextContent("1");

    await user.click(screen.getByRole("button", { name: "set english" }));
    expect(apiMocks.fetchRestrictionLayers).toHaveBeenCalledTimes(1);
  });
});
