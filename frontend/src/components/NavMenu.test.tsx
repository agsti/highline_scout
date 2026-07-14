import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionAreaMode } from "@/types/highliner";
import { NavMenu } from "./NavMenu";

function renderMenu() {
  const onAbout = vi.fn();
  const onFeedback = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState<RestrictionAreaMode>("informative");
    return (
      <NavMenu
        open={open}
        onOpenChange={setOpen}
        onAbout={onAbout}
        onFeedback={onFeedback}
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

  return { onAbout, onFeedback };
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

  it("links to the methodology page for the selected language", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);

    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute(
      "href",
      "/en/how-it-works",
    );

    await user.click(screen.getByRole("button", { name: "Español" }));

    expect(screen.getByRole("link", { name: "Cómo funciona" })).toHaveAttribute(
      "href",
      "/es/how-it-works",
    );
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();
  });

  it("asks for the feedback dialog and closes", async () => {
    const user = userEvent.setup();
    const { onFeedback } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(onFeedback).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();
  });

  it("switches language without closing the panel", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Español" }));

    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Acerca de Highline Scout" })).toBeInTheDocument();
  });

  it("changes the restriction-area mode between both choices", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);

    expect(screen.getByText("Restriction areas")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent(
      "Informative",
    );

    await user.click(screen.getByRole("combobox", { name: "Restriction areas" }));
    await user.click(screen.getByRole("option", { name: "Exclude" }));

    expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent(
      "Exclude",
    );
  });
});
