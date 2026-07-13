import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { AboutDialog } from "./AboutDialog";

describe("AboutDialog", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("credits the data sources and discloses the anonymous, cookieless analytics", () => {
    render(
      <I18nProvider>
        <AboutDialog open onOpenChange={vi.fn()} />
      </I18nProvider>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Highline Scout helps you find spots.");
    expect(dialog).toHaveTextContent("Elevation data © ICGC.");
    expect(dialog).toHaveTextContent("No cookies, no tracking across visits.");
  });
});
