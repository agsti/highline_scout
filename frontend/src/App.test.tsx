import { useEffect, type ReactNode } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ErrorToast } from "./components/ErrorToast";
import { I18nProvider, useI18n } from "./lib/i18n";

const apiMocks = vi.hoisted(() => ({
  fetchRestrictionLayers: vi.fn(),
}));

let publishMapStatus: ((status: string) => void) | undefined;
let publishMapError: ((message: string) => void) | undefined;
let dismissMapError: ((eventId: number) => void) | undefined;

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: apiMocks.fetchRestrictionLayers,
}));

vi.mock("./components/map/MapView", () => ({
  MapView: ({
    showAnchors,
    enabledRestrictions,
    restrictionLayers,
    onMapStatus,
    onError,
  }: {
    showAnchors?: boolean;
    enabledRestrictions?: string[];
    restrictionLayers?: Array<{ id: string }>;
    onMapStatus?: (status: string) => void;
    onError?: (message: string) => void;
  }) => {
    publishMapStatus = onMapStatus;
    publishMapError = onError;
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
  AppShell: ({ chrome, map }: { chrome: ReactNode; map: ReactNode }) => (
    <div>
      <div>{chrome}</div>
      <div>{map}</div>
    </div>
  ),
}));

vi.mock("./components/MapChrome", () => ({
  MapChrome: ({
    filters,
    restrictions,
    errorMessage,
    errorEventId,
    onErrorDismiss,
  }: {
    filters: ReactNode;
    restrictions: ReactNode;
    errorMessage: string;
    errorEventId: number;
    onErrorDismiss: (eventId: number) => void;
  }) => (
    <div>
      {(() => {
        dismissMapError = onErrorDismiss;
        return null;
      })()}
      {filters}
      {restrictions}
      <ErrorToast message={errorMessage} eventId={errorEventId} onDismiss={onErrorDismiss} />
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
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("does not show the map status in the chrome", async () => {
    renderApp();

    await screen.findByText("restrictions");
    await act(async () => {});
    expect(screen.queryByText("3 zones")).not.toBeInTheDocument();
  });

  it("shows map errors in a toast and dismisses them automatically", async () => {
    vi.useFakeTimers();
    renderApp();

    await act(async () => {});
    act(() => publishMapError?.("Error: zones unavailable"));
    expect(screen.getByRole("alert")).toHaveTextContent("Error: zones unavailable");

    act(() => vi.advanceTimersByTime(5000));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not restart the toast deadline after an unrelated App rerender", async () => {
    vi.useFakeTimers();
    renderApp();

    await act(async () => {});
    act(() => publishMapError?.("Error: zones unavailable"));
    act(() => vi.advanceTimersByTime(2_000));
    act(() => screen.getByRole("button", { name: "set english" }).click());

    act(() => vi.advanceTimersByTime(2_999));
    expect(screen.getByRole("alert")).toHaveTextContent("Error: zones unavailable");

    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not dismiss a newer error when an older event is dismissed", async () => {
    renderApp();

    await act(async () => {});
    act(() => publishMapError?.("Error: zones unavailable"));
    act(() => publishMapError?.("Error: anchors unavailable"));
    act(() => dismissMapError?.(1));

    expect(screen.getByRole("alert")).toHaveTextContent("Error: anchors unavailable");
  });

  it("shows restriction metadata errors in the shared toast", async () => {
    window.localStorage.setItem("lang", "ca");
    apiMocks.fetchRestrictionLayers.mockRejectedValue({
      name: "RequestError",
      detail: "metadata unavailable",
    });
    renderApp();

    expect(await screen.findByRole("alert")).toHaveTextContent("Error: metadata unavailable");
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
