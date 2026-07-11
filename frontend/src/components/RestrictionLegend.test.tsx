import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { RestrictionLegend } from "./RestrictionLegend";

const layers: RestrictionLayerMeta[] = [
  { id: "zepa", label: "ZEPA (Aves)", tooltip: "", highlight: "", color: "#e31a1c" },
  { id: "zec", label: "ZEC / LIC", tooltip: "", highlight: "", color: "#ff7f00" },
  { id: "enp", label: "Espacios Naturales Protegidos", tooltip: "", highlight: "", color: "#6a3d9a" },
];

function renderLegend(enabled: string[]) {
  return render(
    <I18nProvider>
      <RestrictionLegend layers={layers} enabled={enabled} />
    </I18nProvider>,
  );
}

describe("RestrictionLegend", () => {
  it("renders nothing when no layer is enabled", () => {
    const { container } = renderLegend([]);

    expect(container).toBeEmptyDOMElement();
  });

  it("names and colours every enabled layer", () => {
    renderLegend(["zepa", "enp"]);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("ZEPA (Aves)");
    expect(items[0].querySelector("span[aria-hidden]")).toHaveStyle({
      backgroundColor: "#e31a1c",
    });
    expect(items[1]).toHaveTextContent("Espacios Naturales Protegidos");
    expect(items[1].querySelector("span[aria-hidden]")).toHaveStyle({
      backgroundColor: "#6a3d9a",
    });
  });

  it("orders the legend by the layer list, not by the order they were enabled", () => {
    renderLegend(["enp", "zepa"]);

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("ZEPA (Aves)");
    expect(items[1]).toHaveTextContent("Espacios Naturales Protegidos");
  });

  it("ignores an enabled id that has no layer metadata", () => {
    renderLegend(["ghost", "zepa"]);

    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});
