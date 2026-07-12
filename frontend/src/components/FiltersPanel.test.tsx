import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FiltersPanel } from "./FiltersPanel";

function renderPanel() {
  render(
    <I18nProvider>
      <FiltersPanel
        filters={<div>panel filters</div>}
        restrictions={<div>panel restrictions</div>}
        statuses={<div>panel statuses</div>}
        swatches={["#e31a1c"]}
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

  it("discloses the restriction layers from the footer row", async () => {
    const user = userEvent.setup();
    renderPanel();

    const disclosure = screen.getByRole("button", { name: /restrictions/i });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");

    await user.click(disclosure);

    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("panel restrictions")).toBeInTheDocument();
  });
});
