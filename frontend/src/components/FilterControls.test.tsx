import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FilterControls, type LengthRange } from "./FilterControls";

function renderControls(overrides: Partial<ComponentProps<typeof FilterControls>> = {}) {
  const props = {
    lengthRange: [20, 150] as LengthRange,
    minExposure: 30,
    showAnchors: true,
    canApply: false,
    onLengthRangeChange: vi.fn(),
    onMinExposureChange: vi.fn(),
    onShowAnchorsChange: vi.fn(),
    onApply: vi.fn(),
    ...overrides,
  };
  render(
    <I18nProvider>
      <FilterControls {...props} />
    </I18nProvider>,
  );
  return props;
}

const applyButton = () => screen.getByRole("button", { name: /apply filters/i });

describe("FilterControls", () => {
  it("disables Apply when the draft matches what is on the map", () => {
    renderControls({ canApply: false });
    expect(applyButton()).toBeDisabled();
  });

  it("enables Apply once there is a pending change", () => {
    renderControls({ canApply: true });
    expect(applyButton()).toBeEnabled();
  });

  it("calls onApply when Apply is pressed", async () => {
    const user = userEvent.setup();
    const props = renderControls({ canApply: true });
    await user.click(applyButton());
    expect(props.onApply).toHaveBeenCalledTimes(1);
  });

  it("reports slider moves as draft changes without applying them", async () => {
    const user = userEvent.setup();
    const props = renderControls({ canApply: false });

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    expect(props.onLengthRangeChange).toHaveBeenCalledWith([21, 150]);
    expect(props.onApply).not.toHaveBeenCalled();
  });
});
