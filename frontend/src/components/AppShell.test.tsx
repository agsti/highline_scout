import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { AppShell } from "./AppShell";
import { FilterPill } from "./FilterPill";
import { FloatingNav } from "./FloatingNav";
import { MobileControlSheet } from "./MobileControlSheet";
import { Dialog, DialogContent } from "./ui/dialog";

// The sheet is controlled by App, so these tests supply the open state it owns —
// and the filter pill is the only thing that opens it.
function ControlledMobileControlSheet() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <FilterPill summary="20–150 m · exp ≥30 m" onClick={() => setOpen(true)} />
      <MobileControlSheet
        filters={<div>sheet filters</div>}
        restrictions={<div>sheet restrictions</div>}
        caveat="Zones to scout"
        open={open}
        onOpenChange={setOpen}
      />
    </>
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
      <AppShell map={<div>map area</div>} chrome={<div>floating chrome</div>} />
    </I18nProvider>,
  );
}

describe("AppShell", () => {
  it("renders the full-bleed map under the floating chrome", () => {
    renderShell();
    expect(screen.getByText("map area")).toBeInTheDocument();
    expect(screen.getByText("floating chrome")).toBeInTheDocument();
  });

  it("opens the filter sheet from the filter pill and exposes the localized close label", async () => {
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

  it("renders the opened mobile sheet above the floating chrome", async () => {
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
      return <AppShell map={<div>{t("mapLoading")}</div>} chrome={null} />;
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

  it("renders exactly one language switcher across the nav and the mobile sheet", async () => {
    const user = userEvent.setup();

    render(
      <I18nProvider>
        <AppShell
          map={<div>map area</div>}
          chrome={
            <>
              <FloatingNav onAbout={() => {}} />
              <ControlledMobileControlSheet />
            </>
          }
        />
      </I18nProvider>,
    );

    // The sheet body only mounts once open, so open it before counting —
    // otherwise a duplicate switcher inside the sheet is invisible to getAllByRole.
    await user.click(screen.getByRole("button", { name: /obre controls|open controls|abrir controles/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // The open (modal) sheet marks the rest of the page aria-hidden, so the query
    // must opt in to hidden elements to still see the nav switcher.
    expect(screen.getAllByRole("group", { name: "Idioma", hidden: true })).toHaveLength(1);
  });
});
