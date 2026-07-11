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
  fetchRestrictionLayers: vi.fn().mockResolvedValue([]),
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
});
