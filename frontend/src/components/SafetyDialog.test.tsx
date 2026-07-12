import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { SafetyDialog } from "./SafetyDialog";

describe("SafetyDialog", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("keeps the safety caveat and the restriction credit", () => {
    render(
      <I18nProvider>
        <SafetyDialog open onOpenChange={vi.fn()} />
      </I18nProvider>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Rigging a highline is dangerous and can be fatal.");
    expect(dialog).toHaveTextContent("Zones to scout");
    expect(dialog).toHaveTextContent("Protected-area data © MITECO");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
