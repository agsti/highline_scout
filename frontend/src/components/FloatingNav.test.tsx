import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { AboutDialog } from "./AboutDialog";
import { FloatingNav } from "./FloatingNav";

function renderNav() {
  const onAbout = vi.fn();
  const onSafety = vi.fn();
  render(
    <I18nProvider>
      <FloatingNav onAbout={onAbout} onSafety={onSafety} />
    </I18nProvider>,
  );
  return { onAbout, onSafety };
}

describe("FloatingNav", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("renders the brand and the menu button, and no loose language or info controls", () => {
    renderNav();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Language" })).not.toBeInTheDocument();
  });

  it("reaches the about dialog through the menu", async () => {
    const user = userEvent.setup();
    const { onAbout } = renderNav();

    await user.click(screen.getByRole("button", { name: "Menu" }));
    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
  });

  it("raises the nav above the scrim while the menu is open", async () => {
    const user = userEvent.setup();
    renderNav();

    expect(screen.getByRole("banner")).toHaveClass("z-[1000]");

    await user.click(screen.getByRole("button", { name: "Menu" }));

    expect(screen.getByRole("banner")).toHaveClass("z-[1120]");
  });
});

describe("AboutDialog", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("shows what the app is and credits the data sources", () => {
    render(
      <I18nProvider>
        <AboutDialog open onOpenChange={vi.fn()} />
      </I18nProvider>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Highline Scout helps you find spots.");
    expect(dialog).toHaveTextContent("Elevation data © ICGC");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
