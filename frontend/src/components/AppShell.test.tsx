import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { AppShell } from "./AppShell";
import { MobileControlSheet } from "./MobileControlSheet";
import { Dialog, DialogContent } from "./ui/dialog";

function setTestLanguage(lang: string) {
  const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");
  const originalLang = document.documentElement.lang;
  const store = new Map<string, string>([["lang", lang]]);

  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
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
    },
  });

  return () => {
    if (originalStorage) {
      Object.defineProperty(window, "localStorage", originalStorage);
    }
    if (originalLang) {
      document.documentElement.lang = originalLang;
    } else {
      document.documentElement.removeAttribute("lang");
    }
  };
}

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
    const restoreLang = setTestLanguage("es");

    try {
      render(
        <I18nProvider>
          <MobileControlSheet
            region="Montserrat"
            summary="Longitud maxima 150 m"
            filters={<div>sheet filters</div>}
            statuses={<div>sheet status</div>}
            restrictions={<div>sheet restrictions</div>}
            caveat="Zones to scout"
            actions={<div>sheet actions</div>}
          />
        </I18nProvider>,
      );

      await user.click(screen.getByRole("button", { name: "Abrir controles" }));

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("sheet filters")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Cerrar controles" })).toBeInTheDocument();
    } finally {
      restoreLang();
    }
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

    const restoreLang = setTestLanguage("es");

    try {
      render(
        <I18nProvider>
          <LocalizedDialog />
        </I18nProvider>,
      );

      expect(screen.getByRole("button", { name: "Cerrar controles" })).toBeInTheDocument();
    } finally {
      restoreLang();
    }
  });
});
