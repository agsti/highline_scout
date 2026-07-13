import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { SafetyDisclaimerDialog } from "./SafetyDisclaimerDialog";

describe("SafetyDisclaimerDialog", () => {
  // The gate now rebuilds on the ui/dialog.tsx Radix primitive (see finding 2:
  // the hand-rolled div had no focus trap, so a keyboard user could tab past it
  // into the nav menu). Radix's modal Dialog marks document.body
  // `pointer-events: none` while open -- that's the primitive's own inertness
  // guarantee, replacing the informal "the overlay div happens to sit on top"
  // blocking the old hand-rolled version relied on. This assertion is the one
  // pre-existing check that had to change: it used to assert the body was left
  // interactive ("") because the gate didn't touch it; now the body is
  // correctly locked ("none") by the primitive itself.
  it("locks body pointer events while open, matching the other Radix dialogs", () => {
    const { unmount } = render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    expect(document.body.style.pointerEvents).toBe("none");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ho entenc|i understand|lo entiendo/i })).toBeInTheDocument();

    unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("keeps the rest of the app inert while the gate is open", () => {
    render(
      <I18nProvider>
        {/* Stands in for the nav's Menu button, which the branch made reachable
            behind the gate (see finding 2). It must be unreachable by role
            query while the gate is open -- that's what a real focus trap plus
            aria-hidden background gives us for free. */}
        <button type="button">Menu</button>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    expect(screen.queryByRole("button", { name: "Menu" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ho entenc|i understand|lo entiendo/i })).toBeInTheDocument();
  });

  it("cannot be dismissed by Escape or by clicking outside the panel", async () => {
    const user = userEvent.setup();

    render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // Click on the overlay, outside the dialog panel.
    const overlay = document.querySelector('[data-state="open"][class*="fixed inset-0"]');
    expect(overlay).not.toBeNull();
    await user.click(overlay as Element);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("calls onAccept from the disclaimer action", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();

    render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={onAccept} />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /ho entenc|i understand|lo entiendo/i }));
    expect(onAccept).toHaveBeenCalledTimes(1);
  });

  it("discloses the anonymous, cookieless analytics", () => {
    render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    expect(screen.getByText(/sense galetes|sin cookies|no cookies/i)).toBeInTheDocument();
  });
});
