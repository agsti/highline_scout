import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

function renderSwitcher() {
  return render(
    <I18nProvider>
      <LanguageSwitcher />
    </I18nProvider>,
  );
}

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "ca");
  });

  it("shows every language as a segment and presses the active one", () => {
    renderSwitcher();

    expect(screen.getByRole("group", { name: "Idioma" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Català" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches language when a segment is clicked", async () => {
    const user = userEvent.setup();
    renderSwitcher();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
  });
});

describe("LanguageSwitcher segmented variant", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "ca");
  });

  it("wraps the segments in an accent track and lifts the active one", () => {
    render(
      <I18nProvider>
        <LanguageSwitcher variant="segmented" />
      </I18nProvider>,
    );

    expect(screen.getByRole("group", { name: "Idioma" })).toHaveClass("bg-accent");
    expect(screen.getByRole("button", { name: "Català" })).toHaveClass("bg-card");
    expect(screen.getByRole("button", { name: "Español" })).not.toHaveClass("bg-card");
  });

  it("still switches language in the segmented variant", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LanguageSwitcher variant="segmented" />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
  });
});
