import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FilterPill } from "./FilterPill";

describe("FilterPill", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("shows the applied summary and opens the sheet when tapped", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <I18nProvider>
        <FilterPill summary="20–150 m · exp ≥30 m" onClick={onClick} />
      </I18nProvider>,
    );

    const pill = screen.getByTestId("filter-pill");
    expect(pill).toHaveTextContent("Filters");
    expect(pill).toHaveTextContent("20–150 m · exp ≥30 m");
    expect(pill).toHaveClass("bg-primary");

    await user.click(screen.getByRole("button", { name: "Open controls" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
