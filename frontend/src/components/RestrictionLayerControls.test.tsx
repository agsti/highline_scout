import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { RestrictionLayerControls } from "./RestrictionLayerControls";

const layers: RestrictionLayerMeta[] = [
  { id: "zepa", label: "ZEPA (Aves)", tooltip: "tooltip", highlight: "highlight", color: "#ff0000" },
];

describe("RestrictionLayerControls", () => {
  it("shows the MITECO data attribution", () => {
    render(
      <I18nProvider>
        <RestrictionLayerControls layers={layers} enabled={[]} onEnabledChange={vi.fn()} />
      </I18nProvider>,
    );

    expect(screen.getByText(/© MITECO/)).toBeInTheDocument();
  });
});
