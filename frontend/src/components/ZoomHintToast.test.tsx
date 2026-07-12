import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { ZOOM_HINT_MS, ZoomHintToast } from "./ZoomHintToast";

function renderToast(active: boolean) {
  return render(
    <I18nProvider>
      <ZoomHintToast active={active} />
    </I18nProvider>,
  );
}

describe("ZoomHintToast", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "es");
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays hidden until density mode is entered", () => {
    renderToast(false);

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows the hint on entry and dismisses it on its own", () => {
    const { rerender } = renderToast(false);

    rerender(
      <I18nProvider>
        <ZoomHintToast active />
      </I18nProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Amplía para ver zonas");

    act(() => {
      vi.advanceTimersByTime(ZOOM_HINT_MS);
    });

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows the hint again the next time density mode is entered", () => {
    const { rerender } = renderToast(true);

    act(() => {
      vi.advanceTimersByTime(ZOOM_HINT_MS);
    });
    expect(screen.queryByRole("status")).toBeNull();

    // Zoom in (leave density mode), then back out again.
    rerender(
      <I18nProvider>
        <ZoomHintToast active={false} />
      </I18nProvider>,
    );
    rerender(
      <I18nProvider>
        <ZoomHintToast active />
      </I18nProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Amplía para ver zonas");
  });
});
