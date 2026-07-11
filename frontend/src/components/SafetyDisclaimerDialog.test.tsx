import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { SafetyDisclaimerDialog } from "./SafetyDisclaimerDialog";

describe("SafetyDisclaimerDialog", () => {
  it("does not lock body pointer events while open", () => {
    const { unmount } = render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    expect(document.body.style.pointerEvents).toBe("");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ho entenc|i understand|lo entiendo/i })).toBeInTheDocument();

    unmount();
    expect(document.body.style.overflow).toBe("");
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
