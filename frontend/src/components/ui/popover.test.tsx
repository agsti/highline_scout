import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

describe("Popover", () => {
  it("opens the panel and tags it with the map-pane z-index", async () => {
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

  it("defaults to end alignment when align/sideOffset are not specified", async () => {
    const user = userEvent.setup();

    render(
      <Popover>
        <PopoverTrigger aria-label="Open">trigger</PopoverTrigger>
        <PopoverContent>panel</PopoverContent>
      </Popover>,
    );

    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(screen.getByText("panel")).toHaveAttribute("data-align", "end");
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
