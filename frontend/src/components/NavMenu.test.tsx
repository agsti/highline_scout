import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionAreaMode } from "@/types/highliner";
import { NavMenu } from "./NavMenu";

function renderMenu() {
  const onAbout = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState<RestrictionAreaMode>("informative");
    return (
      <NavMenu
        open={open}
        onOpenChange={setOpen}
        onAbout={onAbout}
        restrictionAreaMode={mode}
        onRestrictionAreaModeChange={setMode}
      />
    );
  }

  render(
    <I18nProvider>
      <Harness />
    </I18nProvider>,
  );

  return { onAbout };
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Menu" }));
}

describe("NavMenu", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("opens the panel from the menu button", async () => {
    const user = userEvent.setup();
    renderMenu();

    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();

    await openMenu(user);

    expect(screen.getByRole("button", { name: "About Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeInTheDocument();
  });

  it("orders areas, language, feedback, and about without a safety action", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);

    const content = screen.getByRole("dialog", { name: "Menu" });
    const text = content.textContent ?? "";
    const areas = text.indexOf("Restriction areas");
    const language = text.indexOf("Language");
    const feedback = text.indexOf("Send feedback");
    const about = text.indexOf("About Highline Scout");

    expect(areas).toBeGreaterThanOrEqual(0);
    expect(language).toBeGreaterThanOrEqual(0);
    expect(feedback).toBeGreaterThanOrEqual(0);
    expect(about).toBeGreaterThanOrEqual(0);
    expect(areas).toBeLessThan(language);
    expect(language).toBeLessThan(feedback);
    expect(feedback).toBeLessThan(about);
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("asks for the about dialog and closes", async () => {
    const user = userEvent.setup();
    const { onAbout } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();
  });

  it("announces that feedback is not built yet, without closing", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    const feedbackButton = screen.getByRole("button", { name: "Send feedback" });
    const hint = feedbackButton.querySelector('[aria-live="polite"]');
    expect(hint).toBeInTheDocument();
    expect(hint).toHaveTextContent("");

    await user.click(feedbackButton);

    expect(hint).toHaveTextContent("Coming soon");
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About Highline Scout" })).toBeInTheDocument();
  });

  it("switches language without closing the panel", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Español" }));

    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Acerca de Highline Scout" })).toBeInTheDocument();
  });

  it("changes the restriction-area mode between all three choices", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);

    expect(screen.getByText("Restriction areas")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent(
      "Informative",
    );

    await user.click(screen.getByRole("combobox", { name: "Restriction areas" }));
    await user.click(screen.getByRole("option", { name: "Exclude overlaps" }));

    expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent(
      "Exclude overlaps",
    );

    await user.click(screen.getByRole("combobox", { name: "Restriction areas" }));
    await user.click(screen.getByRole("option", { name: "Exclude inside" }));

    expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent(
      "Exclude inside",
    );
  });
});
