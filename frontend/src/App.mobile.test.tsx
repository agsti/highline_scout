import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

vi.mock("./lib/analytics", () => ({
  capture: vi.fn(),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchCountries: vi.fn().mockResolvedValue([]),
  fetchRestrictionLayers: vi.fn().mockResolvedValue([
    { id: "zepa", label: "ZEPA (Aves)", tooltip: "tooltip", highlight: "highlight", color: "#e31a1c" },
  ]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));

describe("mobile control sheet", () => {
  it("closes itself when the filters are applied", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    // The safety disclaimer is also a role="dialog", and it is open on load.
    // Dismiss it first so the sheet is the only dialog in play.
    await user.click(screen.getByRole("button", { name: /i understand/i }));

    await user.click(screen.getByRole("button", { name: /open controls/i }));

    const sheet = await screen.findByRole("dialog");
    const sliders = within(sheet).getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    await user.click(within(sheet).getByRole("button", { name: /apply filters/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("summarises the applied filters, not the drafts", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));

    const pill = screen.getByTestId("filter-pill");
    expect(within(pill).getByText("20–150 m · exp ≥30 m")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /open controls/i }));
    const sheet = await screen.findByRole("dialog");
    const sliders = within(sheet).getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    // Dragging a slider is only a draft — the pill must still describe the map.
    expect(within(pill).getByText("20–150 m · exp ≥30 m")).toBeInTheDocument();

    await user.click(within(sheet).getByRole("button", { name: /apply filters/i }));

    await waitFor(() =>
      expect(within(pill).getByText("21–150 m · exp ≥30 m")).toBeInTheDocument(),
    );
  });

  it("legends the restriction layers drawn on the map", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));

    expect(screen.queryByTestId("legend-chip")).toBeNull();

    await user.click(screen.getByRole("button", { name: /open controls/i }));
    const sheet = await screen.findByRole("dialog");
    await user.click(await within(sheet).findByRole("checkbox", { name: /ZEPA/ }));

    await user.click(within(sheet).getByRole("button", { name: /close controls/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(within(screen.getByTestId("legend-chip")).getByText("ZEPA (Aves)")).toBeInTheDocument();
  });

  it("opens the sheet when the pill summary is tapped", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const pill = screen.getByTestId("filter-pill");

    // Tapping the summary inside the pill must open the sheet, not just the icon.
    await user.click(within(pill).getByText("20–150 m · exp ≥30 m"));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
