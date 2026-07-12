import { fireEvent, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useI18n } from "@/lib/i18n";
import {
  copyViewportLink,
  MapContextMenu,
  type ContextMenuPoint,
} from "./MapContextMenu";

const POINT: ContextMenuPoint = {
  lat: 41.5,
  lng: 1.9,
  zoom: 13,
  x: 120,
  y: 80,
};

const t: ReturnType<typeof useI18n>["t"] = (key) => key;
const originalLocation = window.location;
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
  }
});

describe("MapContextMenu", () => {
  it("dismisses an open menu when Escape is pressed", async () => {
    const onDismiss = vi.fn();
    render(<MapContextMenu point={POINT} t={t} onDismiss={onDismiss} />);

    await userEvent.setup().keyboard("{Escape}");

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("dismisses an open menu when a pointer lands outside it", () => {
    const onDismiss = vi.fn();
    render(<MapContextMenu point={POINT} t={t} onDismiss={onDismiss} />);

    fireEvent.pointerDown(document.body);

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("uses clipboard text for the viewport URL and falls back to prompt", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: new URL("https://example.com/"),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    await copyViewportLink(41.5, 1.9, 13, t);

    expect(writeText).toHaveBeenCalledWith(
      "https://example.com/?lat=41.50000&lng=1.90000&z=13",
    );

    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    const prompt = vi.spyOn(window, "prompt").mockReturnValue(null);

    await copyViewportLink(41.5, 1.9, 13, t);

    expect(prompt).toHaveBeenCalledWith(
      "copyLink",
      "https://example.com/?lat=41.50000&lng=1.90000&z=13",
    );
  });
});
