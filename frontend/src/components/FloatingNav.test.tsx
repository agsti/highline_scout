import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { AboutDialog } from "./AboutDialog";
import { FloatingNav } from "./FloatingNav";

function renderNav() {
  const onAbout = vi.fn();
  render(
    <I18nProvider>
      <FloatingNav onAbout={onAbout} />
    </I18nProvider>,
  );
  return { onAbout };
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

  it("styles the menu trigger as a solid labelled pill", () => {
    renderNav();

    const trigger = screen.getByRole("button", { name: "Menu" });
    expect(trigger).toHaveClass("bg-card", "rounded-full", "shadow-pill");
    expect(trigger).toHaveTextContent("Menu");
    expect(trigger.querySelectorAll("span")[1]).toHaveClass("bg-primary", "text-primary-foreground");
    expect(trigger.querySelector("svg")).toHaveAttribute("stroke-width", "2.5");
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
