import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ERROR_TOAST_MS, ErrorToast } from "./ErrorToast";

describe("ErrorToast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("announces the message and dismisses it after the timeout", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();

    render(<ErrorToast message="Could not load zones" eventId={1} onDismiss={onDismiss} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load zones");

    act(() => {
      vi.advanceTimersByTime(ERROR_TOAST_MS);
    });

    expect(onDismiss).toHaveBeenCalledWith(1);
  });

  it("restarts the dismissal timeout for a new error event", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    const { rerender } = render(
      <ErrorToast message="Could not load zones" eventId={1} onDismiss={onDismiss} />,
    );

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    rerender(<ErrorToast message="Could not load anchors" eventId={2} onDismiss={onDismiss} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load anchors");

    act(() => {
      vi.advanceTimersByTime(ERROR_TOAST_MS - 1);
    });
    expect(onDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onDismiss).toHaveBeenCalledWith(2);
  });
});
