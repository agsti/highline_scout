import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { FiltersPanel } from "./FiltersPanel";
import { RestrictionLayerControls } from "./RestrictionLayerControls";

const restrictionLayers: RestrictionLayerMeta[] = [
  {
    id: "zepa",
    label: "ZEPA (Aves)",
    tooltip: "ZEPA definition",
    highlight: "definition",
    color: "#ff0000",
  },
  {
    id: "zec",
    label: "ZEC / LIC",
    tooltip: "ZEC definition",
    highlight: "definition",
    color: "#00ff00",
  },
];

function renderPanel() {
  render(
    <I18nProvider>
      <FiltersPanel
        filters={<div>panel filters</div>}
        restrictions={<div>panel restrictions</div>}
        statuses={<div>panel statuses</div>}
      />
    </I18nProvider>,
  );
}

describe("FiltersPanel", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("renders the filter form and collapses to its header", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByText("panel filters")).toBeInTheDocument();
    expect(screen.getByText("panel statuses")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Minimize panel" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Expand panel" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("keeps restrictions visible whenever the filters pane is expanded", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByText("panel restrictions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restrictions" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Minimize panel" }));
    expect(screen.getByRole("button", { name: "Expand panel" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("allows adjacent restriction content to overflow only while expanded", async () => {
    const user = userEvent.setup();
    renderPanel();

    const card = screen.getByTestId("filters-card");
    const content = screen.getByTestId("filters-panel-content");
    expect(card).not.toHaveClass("overflow-hidden");
    expect(content).not.toHaveClass("overflow-hidden");

    await user.click(screen.getByRole("button", { name: "Minimize panel" }));
    expect(card).toHaveClass("overflow-hidden");
    expect(content).toHaveClass("overflow-hidden");
  });

  it("resets an open restriction definition after keyboard collapse and re-expand", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <FiltersPanel
          filters={<div>panel filters</div>}
          restrictions={
            <RestrictionLayerControls
              layers={restrictionLayers}
              enabled={["zepa"]}
              onEnabledChange={vi.fn()}
            />
          }
          statuses={<div>panel statuses</div>}
        />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /About.*ZEPA/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const minimize = screen.getByRole("button", { name: "Minimize panel" });
    minimize.focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{Enter}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    for (const helpButton of screen.getAllByRole("button", { name: /About/i })) {
      expect(helpButton).toHaveAttribute("aria-expanded", "false");
    }
    expect(screen.getByRole("checkbox", { name: /ZEPA/i })).toBeChecked();
  });
});
