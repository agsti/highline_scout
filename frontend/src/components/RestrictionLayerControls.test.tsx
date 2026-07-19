import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { RestrictionLayerControls } from "./RestrictionLayerControls";

const layers: RestrictionLayerMeta[] = [
  {
    id: "zepa",
    label: "ZEPA (Aves)",
    tooltip: "ZEPA tooltip with a highlighted warning.",
    highlight: "highlighted warning",
    color: "#ff0000",
  },
  {
    id: "zec",
    label: "ZEC / LIC",
    tooltip: "ZEC tooltip with another highlighted warning.",
    highlight: "another highlighted warning",
    color: "#00ff00",
  },
];

function renderControls(enabled: string[] = [], country = "spain") {
  window.localStorage.setItem("lang", "en");
  render(
    <I18nProvider>
      <RestrictionLayerControls
        layers={layers}
        enabled={enabled}
        country={country}
        onEnabledChange={vi.fn()}
      />
    </I18nProvider>,
  );
}

describe("RestrictionLayerControls", () => {
  it("shows the MITECO data attribution", () => {
    renderControls();

    expect(screen.getByText(/© MITECO/)).toBeInTheDocument();
  });

  it("shows the FOEN attribution for Switzerland", () => {
    renderControls([], "switzerland");

    expect(screen.getByText(/© FOEN/)).toBeInTheDocument();
    expect(screen.queryByText(/© MITECO/)).not.toBeInTheDocument();
  });

  it("opens one desktop definition at a time and toggles the active definition", async () => {
    const user = userEvent.setup();
    renderControls();

    const zepaInfo = screen.getByRole("button", { name: /About.*ZEPA/i });
    await user.click(zepaInfo);
    expect(zepaInfo).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog")).toHaveTextContent(layers[0].tooltip);

    const zecInfo = screen.getByRole("button", { name: /About.*ZEC/i });
    await user.click(zecInfo);
    expect(zepaInfo).toHaveAttribute("aria-expanded", "false");
    expect(zecInfo).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog")).toHaveTextContent(layers[1].tooltip);

    await user.click(zecInfo);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the definition when clicking outside", async () => {
    const user = userEvent.setup();
    renderControls();
    await user.click(screen.getByRole("button", { name: /About.*ZEPA/i }));
    await user.click(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps a checked restriction definition mobile-only until help is opened", () => {
    renderControls(["zepa"]);

    expect(screen.getByTestId("mobile-restriction-definition")).toHaveTextContent(
      layers[0].tooltip,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
