import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

describe("Popover", () => {
  it("renders the portaled panel above the map panes when opened", async () => {
    const user = userEvent.setup();

    render(
      <Popover>
        <PopoverTrigger aria-label="Open">trigger</PopoverTrigger>
        <PopoverContent>panel</PopoverContent>
      </Popover>,
    );

    expect(screen.queryByText("panel")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(screen.getByText("panel")).toHaveClass("z-[1110]");
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();

    render(
      <Popover>
        <PopoverTrigger aria-label="Open">trigger</PopoverTrigger>
        <PopoverContent>panel</PopoverContent>
      </Popover>,
    );

    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByText("panel")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByText("panel")).not.toBeInTheDocument();
  });
});
