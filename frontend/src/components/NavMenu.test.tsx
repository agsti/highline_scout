import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { NavMenu } from "./NavMenu";

function renderMenu() {
  const onAbout = vi.fn();
  const onSafety = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <NavMenu open={open} onOpenChange={setOpen} onAbout={onAbout} onSafety={onSafety} />
    );
  }

  render(
    <I18nProvider>
      <Harness />
    </I18nProvider>,
  );

  return { onAbout, onSafety };
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
    expect(screen.getByRole("button", { name: "Safety" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeInTheDocument();
  });

  it("asks for the about dialog and closes", async () => {
    const user = userEvent.setup();
    const { onAbout } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("asks for the safety dialog and closes", async () => {
    const user = userEvent.setup();
    const { onSafety } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Safety" }));

    expect(onSafety).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Safety" })).toBeInTheDocument();
  });

  it("switches language without closing the panel", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Español" }));

    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Seguridad" })).toBeInTheDocument();
  });
});
