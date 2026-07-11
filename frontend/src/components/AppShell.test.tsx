import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { AppShell } from "./AppShell";
import { MobileControlSheet } from "./MobileControlSheet";
import { Dialog, DialogContent } from "./ui/dialog";

// The sheet is controlled by App, so these tests supply the open state it owns.
function ControlledMobileControlSheet() {
  const [open, setOpen] = useState(false);
  return (
    <MobileControlSheet
      summary="20–150 m · exp ≥30 m"
      legend={null}
      filters={<div>sheet filters</div>}
      statuses={<div>sheet status</div>}
      restrictions={<div>sheet restrictions</div>}
      caveat="Zones to scout"
      open={open}
      onOpenChange={setOpen}
    />
  );
}

const originalLocalStorageDescriptor = Object.getOwnPropertyDescriptor(window, "localStorage");

type StorageShim = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
  clear: () => void;
};

let storageShim: StorageShim | null = null;
let originalDocumentLangState: { hadLang: boolean; langValue: string | null } | null = null;

function setTestLanguage(lang: string) {
  window.localStorage.setItem("lang", lang);
}

beforeEach(() => {
  const documentElement = document.documentElement;
  originalDocumentLangState = {
    hadLang: documentElement.hasAttribute("lang"),
    langValue: documentElement.getAttribute("lang"),
  };

  const store = new Map<string, string>([["lang", "ca"]]);
  storageShim = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };

  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: storageShim,
  });
});

afterEach(() => {
  storageShim?.clear();
  if (originalLocalStorageDescriptor) {
    Object.defineProperty(window, "localStorage", originalLocalStorageDescriptor);
  }
  storageShim = null;

  if (originalDocumentLangState) {
    if (originalDocumentLangState.hadLang) {
      document.documentElement.setAttribute("lang", originalDocumentLangState.langValue ?? "");
    } else {
      document.documentElement.removeAttribute("lang");
    }
  }

  originalDocumentLangState = null;
});

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

  it("opens the mobile peek-card sheet and exposes the localized close label", async () => {
    const user = userEvent.setup();

    setTestLanguage("es");
    render(
      <I18nProvider>
        <ControlledMobileControlSheet />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Abrir controles" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("sheet filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar controles" })).toBeInTheDocument();
  });

  it("renders the opened mobile sheet above the fixed mobile controls", async () => {
    const user = userEvent.setup();

    render(
      <I18nProvider>
        <ControlledMobileControlSheet />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /obre controls|open controls|abrir controles/i }));

    expect(screen.getByRole("dialog")).toHaveClass("z-[1200]");
  });

  it("localizes the map placeholder through the app i18n catalog", async () => {
    function LocalizedMapShell() {
      const { t } = useI18n();
      return (
        <AppShell
          sidebar={<div>sidebar controls</div>}
          mobileControls={<div>mobile controls</div>}
          map={<div>{t("mapLoading")}</div>}
        />
      );
    }

    setTestLanguage("en");
    render(
      <I18nProvider>
        <LocalizedMapShell />
      </I18nProvider>,
    );

    expect(screen.getByText("Map loading")).toBeInTheDocument();
  });

  it("passes a localized close label through dialog content when the close button is shown", async () => {
    function LocalizedDialog() {
      const { t } = useI18n();
      return (
        <Dialog open>
          <DialogContent closeLabel={t("closeControls")}>
            <div>dialog body</div>
          </DialogContent>
        </Dialog>
      );
    }

    setTestLanguage("es");
    render(
      <I18nProvider>
        <LocalizedDialog />
      </I18nProvider>,
    );

    expect(screen.getByRole("button", { name: "Cerrar controles" })).toBeInTheDocument();
  });

  it("does not leave the document body non-interactive when the mobile sheet is closed", () => {
    render(
      <I18nProvider>
        <ControlledMobileControlSheet />
      </I18nProvider>,
    );

    expect(document.body.style.pointerEvents).toBe("");
  });

  it("renders a top navbar with the brand and the language switcher", () => {
    renderShell();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CA" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ES" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
  });
});
