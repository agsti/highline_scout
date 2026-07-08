import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

describe("Select", () => {
  it("renders the portaled menu above the app shell sidebar", async () => {
    const user = userEvent.setup();

    render(
      <Select defaultValue="alpha">
        <SelectTrigger aria-label="Region">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="alpha">alpha</SelectItem>
          <SelectItem value="beta">beta</SelectItem>
        </SelectContent>
      </Select>,
    );

    await user.click(screen.getByRole("combobox", { name: "Region" }));

    const menu = screen.getByRole("listbox");
    expect(menu).toHaveClass("z-[1200]");
  });
});
