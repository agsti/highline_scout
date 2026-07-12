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
  return onAbout;
}

describe("FloatingNav", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("renders the brand, the language switcher, and the info button", () => {
    renderNav();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About Highline Scout" })).toBeInTheDocument();
  });

  it("asks for the about dialog when the info button is pressed", async () => {
    const user = userEvent.setup();
    const onAbout = renderNav();

    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
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
