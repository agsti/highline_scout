import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { AppShell } from "./AppShell";

function renderShell() {
  return render(
    <I18nProvider>
      <AppShell
        sidebar={<div>sidebar controls</div>}
        mobileControls={<div>mobile controls</div>}
        map={<div>map area</div>}
      />
    </I18nProvider>,
  );
}

describe("AppShell", () => {
  it("renders desktop sidebar, mobile controls, and map slots", () => {
    renderShell();
    expect(screen.getByText("sidebar controls")).toBeInTheDocument();
    expect(screen.getByText("mobile controls")).toBeInTheDocument();
    expect(screen.getByText("map area")).toBeInTheDocument();
  });

  it("toggles desktop sidebar collapsed state", async () => {
    const user = userEvent.setup();
    renderShell();
    const button = screen.getByRole("button", { name: /minimize|minimitza|minimizar/i });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
