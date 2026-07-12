# Nav Menu System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the nav's language + info pill with a single menu button opening a dropdown panel that holds Feedback / About / Safety items and a language footer.

**Architecture:** A new `NavMenu` component built on a new shadcn Radix Popover primitive. `FloatingNav` owns the open state (so it can raise the nav row above the scrim) and renders `NavMenu` where the controls pill used to be. Today's `AboutDialog` is one dialog holding both "about" and "safety" content; it splits into `AboutDialog` + a new `SafetyDialog`, one per menu item. `LanguageSwitcher` gains a `segmented` variant for the panel footer, keeping all language-switching logic in one place.

**Tech Stack:** React 18, TypeScript, Tailwind, shadcn/ui + Radix, lucide-react, Vitest + Testing Library.

Spec: `docs/superpowers/specs/2026-07-12-nav-menu-system-design.md`
Design handoff: `design_handoff_menu_system/README.md` (option 4a)

## Global Constraints

- **Work in `frontend/`.** Run `npm test` / `npm run build` from `frontend/`.
- **Use tokens, never hex.** Every handoff colour already exists: `#114B45` = `primary-deep`, `#FCFDFC` = `card`, `#E6EFE9` = `accent`, `#63807A` = `muted-foreground`, `#E3ECE6` = `hairline`, `#16302A` = `foreground`. The only literal `rgba()` allowed is in the two new `boxShadow` tokens (Task 1) and the scrim (Task 5), because the handoff fixes those alpha values.
- **No account/auth UI.** The handoff's "Entrar / Guarda tus zonas" header row is deliberately omitted — this app has no auth. Do not add `signIn` / `saveYourZones` keys or an account row.
- **`aboutBody` is a placeholder** the user will rewrite: exactly "Highline Scout helps you find spots." (and its ca/es equivalents). Do not polish or expand it.
- **i18n keys must exist in all three of ca/es/en.** `src/lib/i18n/i18n.test.tsx` has a catalog-parity test that fails otherwise.
- **Reuse existing keys** `language` and `about`. Do not add duplicates.
- **No autoformatter.** Match surrounding style by hand: double quotes, semicolons, 2-space indent.
- **Z-index ladder:** scrim `1100` < popover panel `1110` < nav row while open `1120`, and all below the dialogs' `1200`/`1210`.

---

### Task 1: i18n keys and shadow tokens

Foundation with no UI. The parity test already in the repo is the gate.

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts`
- Modify: `frontend/tailwind.config.ts`
- Test: `frontend/src/lib/i18n/i18n.test.tsx` (existing parity test covers this)

**Interfaces:**
- Consumes: nothing.
- Produces: `StringKey`s `menu`, `feedback`, `feedbackComingSoon`, `safety`, `aboutBody`, `aboutData`. Tailwind classes `shadow-menu-button`, `shadow-menu`.

- [ ] **Step 1: Add the six keys to the Catalan block**

In `frontend/src/lib/i18n/strings.ts`, inside `STRINGS.ca`, add after the `about:` line:

```ts
    menu: "Menú",
    feedback: "Envia comentaris",
    feedbackComingSoon: "Ben aviat",
    safety: "Seguretat",
    aboutBody: "Highline Scout t'ajuda a trobar spots.",
    aboutData: "Dades d'elevació © ICGC. Dades d'espais protegits © MITECO.",
```

`STRINGS.ca` is the canonical key set — `export type StringKey = keyof typeof STRINGS.ca` — so this is what defines the new keys.

- [ ] **Step 2: Run the parity test to verify it fails**

Run: `cd frontend && npm test -- i18n`
Expected: FAIL — "keeps every language on the Catalan key set", because `es` and `en` are now missing six keys.

- [ ] **Step 3: Add the same keys to the Spanish and English blocks**

In `STRINGS.es`, after its `about:` line:

```ts
    menu: "Menú",
    feedback: "Enviar comentarios",
    feedbackComingSoon: "Próximamente",
    safety: "Seguridad",
    aboutBody: "Highline Scout te ayuda a encontrar spots.",
    aboutData: "Datos de elevación © ICGC. Datos de espacios protegidos © MITECO.",
```

In `STRINGS.en`, after its `about:` line:

```ts
    menu: "Menu",
    feedback: "Send feedback",
    feedbackComingSoon: "Coming soon",
    safety: "Safety",
    aboutBody: "Highline Scout helps you find spots.",
    aboutData: "Elevation data © ICGC. Protected-area data © MITECO.",
```

- [ ] **Step 4: Run the parity test to verify it passes**

Run: `cd frontend && npm test -- i18n`
Expected: PASS.

- [ ] **Step 5: Add the two shadow tokens**

In `frontend/tailwind.config.ts`, in `theme.extend.boxShadow`, add alongside the existing entries:

```ts
        "menu-button": "0 2px 10px rgba(22,48,42,0.2)",
        menu: "0 12px 36px rgba(22,48,42,0.28)",
```

These are close to but deliberately not the same as `pill` (alpha 0.14) and `panel` (`0 8px 32px`, alpha 0.2) — the handoff calls its values final.

- [ ] **Step 6: Commit**

```bash
cd frontend && npm test -- i18n && npx tsc --noEmit
git add src/lib/i18n/strings.ts tailwind.config.ts
git commit -m "feat(web): add nav menu strings and shadow tokens"
```

---

### Task 2: Popover primitive

**Files:**
- Create: `frontend/src/components/ui/popover.tsx`
- Create: `frontend/src/components/ui/popover.test.tsx`
- Modify: `frontend/package.json` (via `npm install`)

**Interfaces:**
- Consumes: `cn` from `@/lib/utils`.
- Produces: `Popover`, `PopoverTrigger`, `PopoverContent` from `@/components/ui/popover`. `PopoverContent` defaults to `align="end"`, `sideOffset={8}` and carries `z-[1110]`.

Radix **Popover**, not `DropdownMenu`: `DropdownMenu` imposes menu-item semantics and roving tabindex, which fight the language segmented control in the panel footer (three peer `aria-pressed` buttons, none of which should close the panel).

- [ ] **Step 1: Install the dependency**

```bash
cd frontend && npm install @radix-ui/react-popover@^1.1.6
```

Its transitive deps (dismissable-layer, focus-scope, portal, popper, presence) are already present via dialog/select, so this is a small add.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/ui/popover.test.tsx`:

```tsx
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test -- popover`
Expected: FAIL — cannot resolve `./popover`.

- [ ] **Step 4: Write the primitive**

Create `frontend/src/components/ui/popover.tsx`, mirroring the house style of `ui/dialog.tsx`:

```tsx
import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "end", sideOffset = 8, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        // Radix hands us the transform origin of the side/align we resolved to,
        // so the panel scales out of the corner it is anchored to.
        "z-[1110] origin-[var(--radix-popover-content-transform-origin)] overflow-hidden rounded-2xl bg-card text-card-foreground shadow-menu duration-150 focus-visible:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverTrigger, PopoverContent };
```

`rounded-2xl` is 16px, the handoff's panel radius. `align="end"` + `sideOffset={8}` under a 42px button at `top: 14px` lands the panel at exactly `top: 64px`, right-aligned to the button — the handoff's `top: 64px; right: 12px`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npm test -- popover`
Expected: PASS, both cases.

- [ ] **Step 6: Commit**

```bash
cd frontend && npx tsc --noEmit
git add src/components/ui/popover.tsx src/components/ui/popover.test.tsx package.json package-lock.json
git commit -m "feat(web): add popover primitive"
```

---

### Task 3: LanguageSwitcher segmented variant

**Files:**
- Modify: `frontend/src/components/LanguageSwitcher.tsx`
- Modify: `frontend/src/components/LanguageSwitcher.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `<LanguageSwitcher variant="pill" | "segmented" />`, defaulting to `"pill"`. `LANGS`, `setLang`, `SHORT`, `NAMES` are untouched — the variant selects chrome only, so switching logic stays in one place. `SafetyDisclaimerDialog` keeps the default `pill` and needs no change.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/LanguageSwitcher.test.tsx`:

```tsx
describe("LanguageSwitcher segmented variant", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "ca");
  });

  it("wraps the segments in an accent track and lifts the active one", () => {
    render(
      <I18nProvider>
        <LanguageSwitcher variant="segmented" />
      </I18nProvider>,
    );

    expect(screen.getByRole("group", { name: "Idioma" })).toHaveClass("bg-accent");
    expect(screen.getByRole("button", { name: "Català" })).toHaveClass("bg-card");
    expect(screen.getByRole("button", { name: "Español" })).not.toHaveClass("bg-card");
  });

  it("still switches language in the segmented variant", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LanguageSwitcher variant="segmented" />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- LanguageSwitcher`
Expected: FAIL — TS rejects the unknown `variant` prop / the group has no `bg-accent`.

- [ ] **Step 3: Add the variant**

Replace the body of `frontend/src/components/LanguageSwitcher.tsx` (keep `SHORT` and `NAMES` exactly as they are):

```tsx
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const SHORT: Record<Lang, string> = {
  ca: "CA",
  es: "ES",
  en: "EN",
};
const NAMES: Record<Lang, string> = {
  ca: "Català",
  es: "Español",
  en: "English",
};

interface LanguageSwitcherProps {
  // "pill" is the standalone nav/dialog treatment; "segmented" is the track
  // that sits in the nav menu's language footer.
  variant?: "pill" | "segmented";
}

export function LanguageSwitcher({ variant = "pill" }: LanguageSwitcherProps) {
  const { lang, setLang, t } = useI18n();
  const segmented = variant === "segmented";

  return (
    <div
      role="group"
      aria-label={t("language")}
      className={cn(
        "flex items-center gap-0.5",
        segmented ? "rounded-[8px] bg-accent p-0.5" : "pr-1",
      )}
    >
      {LANGS.map((item) => {
        const active = item === lang;

        return (
          <button
            key={item}
            type="button"
            aria-label={NAMES[item]}
            aria-pressed={active}
            onClick={() => setLang(item)}
            className={cn(
              "transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              segmented
                ? "rounded-[6px] px-2 py-1 text-[11px]"
                : "rounded-full px-[9px] py-[7px] text-[11px] md:px-[11px] md:py-2 md:text-xs",
              active && segmented && "bg-card font-bold text-primary-deep shadow-[0_1px_3px_rgba(22,48,42,0.12)]",
              active && !segmented && "bg-primary font-bold text-primary-foreground",
              !active && "font-semibold text-muted-foreground",
              !active && (segmented ? "hover:bg-card/60" : "hover:bg-accent"),
            )}
          >
            {SHORT[item]}
          </button>
        );
      })}
    </div>
  );
}
```

The inactive hover differs by variant on purpose: `hover:bg-accent` is invisible against the segmented track, which is itself `bg-accent`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- LanguageSwitcher`
Expected: PASS — the two new cases plus the two existing `pill` cases, which must not regress.

- [ ] **Step 5: Commit**

```bash
cd frontend && npx tsc --noEmit
git add src/components/LanguageSwitcher.tsx src/components/LanguageSwitcher.test.tsx
git commit -m "feat(web): add segmented variant to LanguageSwitcher"
```

---

### Task 4: Split AboutDialog into About + Safety

Today `AboutDialog` holds everything: safety disclaimer, caveat, MITECO credit and privacy. The menu now has two entries, so the content splits to match. The new `SafetyDialog` test exists specifically so the caveat and MITECO credit cannot be silently dropped in the move.

**Files:**
- Create: `frontend/src/components/SafetyDialog.tsx`
- Create: `frontend/src/components/SafetyDialog.test.tsx`
- Modify: `frontend/src/components/AboutDialog.tsx`

**Interfaces:**
- Consumes: `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle` from `@/components/ui/dialog`; keys from Task 1.
- Produces: `<SafetyDialog open={boolean} onOpenChange={(open: boolean) => void} />` — same prop shape as `AboutDialog`.

**Note:** do not touch `SafetyDisclaimerDialog.tsx`. That is the separate first-run blocking gate, and it stays as it is.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/SafetyDialog.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { SafetyDialog } from "./SafetyDialog";

describe("SafetyDialog", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("keeps the safety caveat and the restriction credit", () => {
    render(
      <I18nProvider>
        <SafetyDialog open onOpenChange={vi.fn()} />
      </I18nProvider>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Rigging a highline is dangerous and can be fatal.");
    expect(dialog).toHaveTextContent("Zones to scout");
    expect(dialog).toHaveTextContent("Protected-area data © MITECO");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
```

(If `STRINGS.en.caveat` does not literally start "Zones to scout", read it in `src/lib/i18n/strings.ts` and assert on a distinctive substring of the real value instead.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- SafetyDialog`
Expected: FAIL — cannot resolve `./SafetyDialog`.

- [ ] **Step 3: Write SafetyDialog**

Create `frontend/src/components/SafetyDialog.tsx`. This is the safety half of the old `AboutDialog`, moved verbatim:

```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

interface SafetyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SafetyDialog({ open, onOpenChange }: SafetyDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("safety")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
          <p>{t("disclaimerBody")}</p>
          <p>{t("disclaimerResponsibility")}</p>
          <p>{t("caveat")}</p>
          <p className="text-xs">{t("restrictionCredit")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- SafetyDialog`
Expected: PASS.

- [ ] **Step 5: Rewrite AboutDialog to the about half**

Replace the content block of `frontend/src/components/AboutDialog.tsx`. Keep the `about` title and the props exactly as they are:

```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutDialog({ open, onOpenChange }: AboutDialogProps) {
  const { t } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("about")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>{t("aboutBody")}</p>
          <p className="text-xs">{t("aboutData")}</p>
          <p className="text-xs">{t("disclaimerPrivacy")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

The safety text is now reachable from the Safety item, so it is not duplicated here.

- [ ] **Step 6: Retarget the existing AboutDialog test**

`frontend/src/components/FloatingNav.test.tsx` currently ends with a `describe("AboutDialog")` block asserting the safety caveat and MITECO credit. Those assertions now belong to `SafetyDialog`. Replace that whole `describe("AboutDialog", ...)` block with:

```tsx
describe("AboutDialog", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("shows what the app is and credits the data sources", () => {
    render(
      <I18nProvider>
        <AboutDialog open onOpenChange={vi.fn()} />
      </I18nProvider>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Highline Scout helps you find spots.");
    expect(dialog).toHaveTextContent("Elevation data © ICGC");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
```

Leave the `describe("FloatingNav")` block above it alone for now — Task 6 rewrites it.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npm test -- SafetyDialog FloatingNav`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd frontend && npx tsc --noEmit
git add src/components/SafetyDialog.tsx src/components/SafetyDialog.test.tsx src/components/AboutDialog.tsx src/components/FloatingNav.test.tsx
git commit -m "feat(web): split safety content out of the about dialog"
```

---

### Task 5: NavMenu

The core of the feature.

**Files:**
- Create: `frontend/src/components/NavMenu.tsx`
- Create: `frontend/src/components/NavMenu.test.tsx`

**Interfaces:**
- Consumes: `Popover`, `PopoverTrigger`, `PopoverContent` (Task 2); `LanguageSwitcher` with `variant="segmented"` (Task 3); keys `menu`, `feedback`, `feedbackComingSoon`, `about`, `safety`, `language` (Task 1).
- Produces:

```ts
interface NavMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAbout: () => void;
  onSafety: () => void;
}
```

**Why `open` is controlled from the parent:** the scrim is portaled to `document.body` at `z-[1100]`, but the nav lives inside a `z-[1000]` header that creates its own stacking context — a descendant cannot paint above the scrim from in there, whatever `z-index` it is given. So `FloatingNav` (Task 6) raises the whole header to `z-[1120]` while the menu is open, and it needs the open state to do that. Hence controlled.

**Dismissal:** scrim tap and Escape (both free from Radix's dismissable layer), plus selecting About or Safety. Changing language does **not** close the panel — the handoff's "dismiss on item selection" refers to the item list; the footer is a control, and closing the panel out from under someone comparing languages would be hostile.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/NavMenu.test.tsx`:

```tsx
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { NavMenu } from "./NavMenu";

function renderMenu() {
  const onAbout = vi.fn();
  const onSafety = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <NavMenu open={open} onOpenChange={setOpen} onAbout={onAbout} onSafety={onSafety} />
    );
  }

  render(
    <I18nProvider>
      <Harness />
    </I18nProvider>,
  );

  return { onAbout, onSafety };
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Menu" }));
}

describe("NavMenu", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("opens the panel from the menu button", async () => {
    const user = userEvent.setup();
    renderMenu();

    expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();

    await openMenu(user);

    expect(screen.getByRole("button", { name: "About Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Safety" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeInTheDocument();
  });

  it("asks for the about dialog and closes", async () => {
    const user = userEvent.setup();
    const { onAbout } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("asks for the safety dialog and closes", async () => {
    const user = userEvent.setup();
    const { onSafety } = renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Safety" }));

    expect(onSafety).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });

  it("announces that feedback is not built yet, without closing", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Safety" })).toBeInTheDocument();
  });

  it("switches language without closing the panel", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Español" }));

    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Seguridad" })).toBeInTheDocument();
  });
});
```

The last case is the load-bearing one: it is the regression guard for the "language footer is a control, not an item" decision. Note it asserts the panel is still open *and* has re-rendered in Spanish.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- NavMenu`
Expected: FAIL — cannot resolve `./NavMenu`.

- [ ] **Step 3: Write NavMenu**

Create `frontend/src/components/NavMenu.tsx`:

```tsx
import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Info, Menu, MessageSquarePlus, ShieldAlert, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAbout: () => void;
  onSafety: () => void;
}

interface MenuItemProps {
  icon: ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}

function MenuItem({ icon, label, hint, onClick }: MenuItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[44px] w-full items-center gap-2.5 rounded-[10px] px-2.5 py-[11px] text-left text-[13px] font-semibold text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <span aria-hidden className="flex shrink-0 text-muted-foreground">
        {icon}
      </span>
      <span className="flex-1">{label}</span>
      {hint ? (
        <span className="text-[11px] font-semibold text-muted-foreground">{hint}</span>
      ) : null}
    </button>
  );
}

export function NavMenu({ open, onOpenChange, onAbout, onSafety }: NavMenuProps) {
  const { t } = useI18n();
  const [feedbackNoted, setFeedbackNoted] = useState(false);

  function handleOpenChange(next: boolean) {
    if (!next) setFeedbackNoted(false);
    onOpenChange(next);
  }

  function select(action: () => void) {
    handleOpenChange(false);
    action();
  }

  return (
    <>
      {/* Portaled to body: the nav header is its own stacking context, so a
          scrim rendered inside it could never cover the map. */}
      {open
        ? createPortal(
            <div aria-hidden className="fixed inset-0 z-[1100] bg-[rgba(22,48,42,0.18)]" />,
            document.body,
          )
        : null}

      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger
          aria-label={t("menu")}
          className="flex h-[42px] w-[42px] items-center justify-center rounded-full bg-primary-deep text-primary-foreground shadow-menu-button transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {open ? (
            <X className="h-4 w-4" strokeWidth={1.6} aria-hidden />
          ) : (
            <Menu className="h-4 w-4" strokeWidth={1.6} aria-hidden />
          )}
        </PopoverTrigger>

        <PopoverContent className="w-[248px] p-0" aria-label={t("menu")}>
          <div className="p-1.5">
            <MenuItem
              icon={<MessageSquarePlus className="h-4 w-4" />}
              label={t("feedback")}
              hint={feedbackNoted ? t("feedbackComingSoon") : undefined}
              onClick={() => setFeedbackNoted(true)}
            />
            <MenuItem
              icon={<Info className="h-4 w-4" />}
              label={t("about")}
              onClick={() => select(onAbout)}
            />
            <MenuItem
              icon={<ShieldAlert className="h-4 w-4" />}
              label={t("safety")}
              onClick={() => select(onSafety)}
            />
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-hairline px-3.5 py-2.5">
            <span className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground">
              {t("language")}
            </span>
            <LanguageSwitcher variant="segmented" />
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- NavMenu`
Expected: PASS, all six cases.

If the language case fails because clicking a segment closes the panel, the cause is Radix treating the click as an outside interaction — it is not, since the switcher is inside `PopoverContent`. Do not "fix" it by suppressing `onOpenChange`; re-check that `LanguageSwitcher` is rendered inside `PopoverContent`.

- [ ] **Step 5: Commit**

```bash
cd frontend && npx tsc --noEmit
git add src/components/NavMenu.tsx src/components/NavMenu.test.tsx
git commit -m "feat(web): add the nav dropdown menu"
```

---

### Task 6: Wire it in and retire the controls pill

**Files:**
- Modify: `frontend/src/components/FloatingNav.tsx`
- Modify: `frontend/src/components/FloatingNav.test.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `NavMenu` (Task 5), `SafetyDialog` (Task 4).
- Produces: `FloatingNav` and `MapChrome` both take `onSafety: () => void` alongside their existing `onAbout: () => void`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/components/FloatingNav.test.tsx`, replace the `describe("FloatingNav", ...)` block (leave the `describe("AboutDialog")` block from Task 4 alone) with:

```tsx
function renderNav() {
  const onAbout = vi.fn();
  const onSafety = vi.fn();
  render(
    <I18nProvider>
      <FloatingNav onAbout={onAbout} onSafety={onSafety} />
    </I18nProvider>,
  );
  return { onAbout, onSafety };
}

describe("FloatingNav", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "en");
  });

  it("renders the brand and the menu button, and no loose language or info controls", () => {
    renderNav();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Language" })).not.toBeInTheDocument();
  });

  it("reaches the about dialog through the menu", async () => {
    const user = userEvent.setup();
    const { onAbout } = renderNav();

    await user.click(screen.getByRole("button", { name: "Menu" }));
    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
  });

  it("raises the nav above the scrim while the menu is open", async () => {
    const user = userEvent.setup();
    renderNav();

    expect(screen.getByRole("banner")).toHaveClass("z-[1000]");

    await user.click(screen.getByRole("button", { name: "Menu" }));

    expect(screen.getByRole("banner")).toHaveClass("z-[1120]");
  });
});
```

Make sure the file still imports what it uses — it needs `useState`-free imports only: `render`, `screen`, `userEvent`, `beforeEach/describe/expect/it/vi`, `I18nProvider`, `AboutDialog`, `FloatingNav`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- FloatingNav`
Expected: FAIL — `FloatingNav` takes no `onSafety`, and there is no "Menu" button.

- [ ] **Step 3: Rewrite FloatingNav**

Replace `frontend/src/components/FloatingNav.tsx` entirely:

```tsx
import { useState } from "react";
import { cn } from "@/lib/utils";
import { BrandPill } from "./BrandPill";
import { NavMenu } from "./NavMenu";

interface FloatingNavProps {
  onAbout: () => void;
  onSafety: () => void;
}

export function FloatingNav({ onAbout, onSafety }: FloatingNavProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header
      className={cn(
        "pointer-events-none absolute inset-x-3 top-3.5 flex items-center justify-between gap-2 md:inset-x-4 md:top-4",
        // The menu's scrim is portaled to body at z-1100, and this header is its
        // own stacking context — so the row has to outrank the scrim from here,
        // or the brand and the menu button would be dimmed along with the map.
        menuOpen ? "z-[1120]" : "z-[1000]",
      )}
    >
      <div className="pointer-events-auto">
        <BrandPill />
      </div>
      <div className="pointer-events-auto">
        <NavMenu
          open={menuOpen}
          onOpenChange={setMenuOpen}
          onAbout={onAbout}
          onSafety={onSafety}
        />
      </div>
    </header>
  );
}
```

The `Info` import, the `useI18n` call and the `LanguageSwitcher` import all go — the menu owns those now.

- [ ] **Step 4: Thread `onSafety` through MapChrome**

In `frontend/src/components/MapChrome.tsx`, add to `MapChromeProps` beside `onAbout`:

```ts
  onSafety: () => void;
```

and pass it down:

```tsx
      <FloatingNav onAbout={props.onAbout} onSafety={props.onSafety} />
```

- [ ] **Step 5: Wire App**

In `frontend/src/App.tsx`:

Add the import beside the others (alphabetical order — after `RestrictionLegend`, before `SafetyDisclaimerDialog`):

```tsx
import { SafetyDialog } from "./components/SafetyDialog";
```

Add the state beside `aboutOpen`:

```tsx
  const [safetyOpen, setSafetyOpen] = useState(false);
```

Pass the handler to `MapChrome`, right after `onAbout`:

```tsx
            onSafety={() => setSafetyOpen(true)}
```

Render the dialog beside `AboutDialog`:

```tsx
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
      <SafetyDialog open={safetyOpen} onOpenChange={setSafetyOpen} />
```

- [ ] **Step 6: Run the full suite and the build**

Run: `cd frontend && npm test`
Expected: PASS. `App.test.tsx`, `App.mobile.test.tsx`, `App.filters.test.tsx` and `AppShell.test.tsx` also render the nav — if any of them assert on the old language segments or the info button, retarget them at the menu button (open the menu first, then assert). Do not delete a failing assertion to make it green; move it.

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean typecheck, successful build.

- [ ] **Step 7: Commit**

```bash
git add src/components/FloatingNav.tsx src/components/FloatingNav.test.tsx src/components/MapChrome.tsx src/App.tsx
git commit -m "feat(web): replace the nav controls pill with the menu"
```

---

## Verification

Beyond the suite, drive the real app once — the tests run in jsdom, which has no layout, so they cannot catch the panel landing in the wrong place or the scrim covering the wrong things.

- [ ] Run `just dev` and `just dev-web`, open `http://localhost:5173`, dismiss the first-run disclaimer.
- [ ] Menu button is a deep-green 42px circle, top-right, opposite the brand pill.
- [ ] Tapping it dims the map (not the nav row) and opens a 248px panel under the button, its top-right corner anchored to the button.
- [ ] About and Safety open their dialogs *above* the menu, and the menu is closed behind them.
- [ ] Feedback shows "Coming soon" and the panel stays open.
- [ ] Switching language re-renders the panel in the new language and the panel stays open.
- [ ] Escape and a tap on the dimmed map both close it.
- [ ] Check at a desktop width too — the menu replaces the old pill at every breakpoint.
