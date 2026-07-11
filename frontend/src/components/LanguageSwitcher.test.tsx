import { render, screen, within } from "@testing-library/react";
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

  it("shows only the current language flag while closed", () => {
    renderSwitcher();

    const trigger = screen.getByRole("combobox", { name: "Idioma" });

    expect(within(trigger).getByRole("img", { name: "Catalan flag" })).toBeInTheDocument();
    expect(within(trigger).queryByText("CA")).not.toBeInTheDocument();
    expect(within(trigger).queryByText("ES")).not.toBeInTheDocument();
    expect(within(trigger).queryByText("EN")).not.toBeInTheDocument();
  });

  it("switches language from the dropdown menu", async () => {
    const user = userEvent.setup();
    renderSwitcher();

    await user.click(screen.getByRole("combobox", { name: "Idioma" }));
    const menu = screen.getByRole("listbox");

    expect(within(menu).queryByText("CA")).not.toBeInTheDocument();
    expect(within(menu).queryByText("ES")).not.toBeInTheDocument();
    expect(within(menu).queryByText("EN")).not.toBeInTheDocument();

    await user.click(screen.getByRole("option", { name: /English/ }));

    const trigger = screen.getByRole("combobox", { name: "Language" });
    const flag = within(trigger).getByRole("img", { name: "English flag" });

    expect(flag).toBeInTheDocument();
    expect(flag.tagName).not.toBe("svg");
  });
});
