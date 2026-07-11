# Top Navbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent top navbar (brand + language switcher) on mobile and desktop, and remove the language-switcher duplicates it replaces.

**Architecture:** A new `NavBar` component is rendered by `AppShell`. `AppShell`'s root becomes a vertical flex column: navbar first, then a `relative flex-1` region holding today's absolutely-positioned sidebar, collapse tab, `<main>`, and mobile controls. Re-parenting is the whole layout change — those children keep their own classes and simply anchor below the navbar. The sidebar and mobile sheet then drop their now-redundant `LanguageSwitcher`, which lets `LanguageSwitcher` lose its `compact` prop.

**Tech Stack:** React 18, TypeScript, Tailwind, shadcn/ui primitives, Vitest + Testing Library.

Spec: `docs/superpowers/specs/2026-07-12-top-navbar-design.md`

## Global Constraints

- No new i18n strings. `Highline Scout` is a proper noun and stays untranslated; the switcher already localizes its `aria-label` via the existing `language` key.
- The navbar is in normal flow (it pushes content down); it must not float over the map.
- `SafetyDisclaimerDialog` keeps its own `LanguageSwitcher` — it blocks the app on first load, so language must be selectable from inside it.
- Run all frontend commands from `frontend/`. Tests: `npm test`. Typecheck+build: `npm run build`.

## File Structure

- Create: `frontend/src/components/NavBar.tsx` — the bar: brand + switcher. No props, no state.
- Modify: `frontend/src/components/AppShell.tsx` — flex column; renders `NavBar` above the existing region.
- Modify: `frontend/src/components/DesktopSidebar.tsx` — drop the `<h1>` and the switcher footer.
- Modify: `frontend/src/components/MobileControlSheet.tsx` — drop the switcher.
- Modify: `frontend/src/components/LanguageSwitcher.tsx` — drop the `compact` prop.
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx` — call site loses `compact`.
- Test: `frontend/src/components/AppShell.test.tsx` — navbar rendering + the single-switcher guard.

---

### Task 1: NavBar component and AppShell restructure

**Files:**
- Create: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Test: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: `LanguageSwitcher` from `./LanguageSwitcher` — in this task it still takes a `compact?: boolean` prop, so `NavBar` passes `compact` to get the label-less form. Task 2 removes that prop.
- Produces: `NavBar` — `export function NavBar(): JSX.Element`, no props. Rendered only by `AppShell`.

- [ ] **Step 1: Write the failing test**

Add this test to the existing `describe("AppShell", ...)` block in `frontend/src/components/AppShell.test.tsx`. It uses the file's existing `renderShell()` helper.

```tsx
  it("renders a top navbar with the brand and the language switcher", () => {
    renderShell();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CA" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ES" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/AppShell.test.tsx`
Expected: FAIL — `Unable to find an accessible element with the role "banner"`.

- [ ] **Step 3: Create the NavBar component**

Create `frontend/src/components/NavBar.tsx`:

```tsx
import { LanguageSwitcher } from "./LanguageSwitcher";

export function NavBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b bg-card px-3 md:px-4">
      <h1 className="text-base font-semibold tracking-tight md:text-lg">Highline Scout</h1>
      <LanguageSwitcher compact />
    </header>
  );
}
```

- [ ] **Step 4: Restructure AppShell around the navbar**

Rewrite `frontend/src/components/AppShell.tsx`. The `<aside>`, the collapse `<Button>`, `<main>`, and the mobile controls keep their existing classes verbatim — they just move inside the new `relative flex-1` region.

```tsx
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { NavBar } from "./NavBar";

interface AppShellProps {
  sidebar: ReactNode;
  mobileControls: ReactNode;
  map: ReactNode;
}

export function AppShell({ sidebar, mobileControls, map }: AppShellProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);
  const expanded = !collapsed;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <NavBar />
      <div className="relative flex-1 overflow-hidden">
        <aside
          className={cn(
            "absolute inset-y-0 left-0 z-[1000] hidden w-80 flex-col border-r bg-card shadow-sm transition-transform duration-200 md:flex",
            collapsed && "-translate-x-80",
          )}
        >
          {sidebar}
        </aside>
        <Button
          type="button"
          size="icon"
          variant="outline"
          aria-label={expanded ? t("panelMinimize") : t("panelExpand")}
          aria-expanded={expanded}
          className={cn(
            "absolute top-1/2 z-[1100] hidden h-14 w-8 -translate-y-1/2 rounded-l-none rounded-r-md bg-card md:inline-flex",
            expanded ? "left-80 -ml-px" : "left-0",
          )}
          onClick={() => setCollapsed((value) => !value)}
        >
          {expanded ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </Button>
        <main className={cn("h-full transition-[padding] duration-200 md:pl-80", collapsed && "md:pl-0")}>
          {map}
        </main>
        <div className="md:hidden">{mobileControls}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS — including the pre-existing AppShell tests (sidebar/map slots, collapse toggle, mobile sheet), which must not regress.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/NavBar.tsx frontend/src/components/AppShell.tsx frontend/src/components/AppShell.test.tsx
git commit -m "feat(web): add a top navbar with the brand and language switcher"
```

---

### Task 2: Remove the duplicated language switchers and the `compact` prop

After Task 1 the switcher appears twice (navbar + sidebar on desktop, navbar + sheet on mobile). This task makes the navbar the only one.

**Files:**
- Modify: `frontend/src/components/DesktopSidebar.tsx`
- Modify: `frontend/src/components/MobileControlSheet.tsx`
- Modify: `frontend/src/components/LanguageSwitcher.tsx`
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Test: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: `NavBar` from Task 1.
- Produces: `LanguageSwitcher` — `export function LanguageSwitcher(): JSX.Element`, **no props**. Always renders the label-less button group. Callers after this task: `NavBar`, `SafetyDisclaimerDialog`.

- [ ] **Step 1: Write the failing guard test**

Add to `frontend/src/components/AppShell.test.tsx`. This renders the real `DesktopSidebar` and the real mobile sheet inside the real `AppShell`, so a switcher coming back in either one fails the test. `SafetyDisclaimerDialog` is not part of this tree, so its own switcher does not interfere.

Add the import at the top of the file, next to the existing `AppShell` / `MobileControlSheet` imports:

```tsx
import { DesktopSidebar } from "./DesktopSidebar";
```

Add the test inside `describe("AppShell", ...)`:

```tsx
  it("renders exactly one language switcher across the navbar, sidebar, and mobile sheet", () => {
    render(
      <I18nProvider>
        <AppShell
          sidebar={
            <DesktopSidebar
              filters={<div>sidebar filters</div>}
              statuses={<div>sidebar status</div>}
              restrictions={<div>sidebar restrictions</div>}
              caveat="Zones to scout"
            />
          }
          mobileControls={<ControlledMobileControlSheet />}
          map={<div>map area</div>}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByRole("button", { name: "CA" })).toHaveLength(1);
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/AppShell.test.tsx`
Expected: FAIL — two "CA" buttons found (navbar + sidebar), so `toHaveLength(1)` fails with received length 2.

- [ ] **Step 3: Drop the switcher and the title from DesktopSidebar**

Rewrite `frontend/src/components/DesktopSidebar.tsx` (props unchanged):

```tsx
import type { ReactNode } from "react";

interface DesktopSidebarProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
}

export function DesktopSidebar({ filters, restrictions, statuses, caveat }: DesktopSidebarProps) {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      {filters}
      {statuses}
      {restrictions}
      <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
        {caveat}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Drop the switcher from MobileControlSheet**

In `frontend/src/components/MobileControlSheet.tsx`, remove the import line:

```tsx
import { LanguageSwitcher } from "./LanguageSwitcher";
```

and remove the `<LanguageSwitcher compact />` line from the sheet body, so that block reads:

```tsx
        <div className="mt-4 space-y-5">
          {props.filters}
          {props.statuses}
          {props.restrictions}
          <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
            {props.caveat}
          </p>
        </div>
```

- [ ] **Step 5: Remove the `compact` prop from LanguageSwitcher**

Both remaining callers want the label-less form, so the prop has one possible value. Rewrite `frontend/src/components/LanguageSwitcher.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LABELS: Record<Lang, string> = { ca: "CA", es: "ES", en: "EN" };

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();

  return (
    <div className="flex gap-1" role="group" aria-label={t("language")}>
      {LANGS.map((item) => (
        <Button
          key={item}
          type="button"
          size="sm"
          variant={item === lang ? "default" : "outline"}
          className={cn("h-8 px-3 text-xs", item === lang && "shadow-sm")}
          aria-pressed={item === lang}
          onClick={() => setLang(item)}
        >
          {LABELS[item]}
        </Button>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Update the two remaining call sites**

In `frontend/src/components/NavBar.tsx`, change `<LanguageSwitcher compact />` to `<LanguageSwitcher />`.

In `frontend/src/components/SafetyDisclaimerDialog.tsx`, change `<LanguageSwitcher compact />` to `<LanguageSwitcher />`.

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS — the new guard passes, and the existing App, i18n, and disclaimer tests are unchanged.

- [ ] **Step 8: Typecheck and build**

Run: `cd frontend && npm run build`
Expected: exit 0. This catches any leftover `compact` prop usage or now-unused import (`tsc -b` runs before the Vite build).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/DesktopSidebar.tsx frontend/src/components/MobileControlSheet.tsx frontend/src/components/LanguageSwitcher.tsx frontend/src/components/SafetyDisclaimerDialog.tsx frontend/src/components/NavBar.tsx frontend/src/components/AppShell.test.tsx
git commit -m "refactor(web): make the navbar the only language switcher"
```

---

## Manual verification (after both tasks)

Run `just dev-web` and check, at a desktop width and a narrow (≤640px) width:

1. The navbar spans the full width above both the sidebar and the map; nothing is hidden behind it.
2. The sidebar starts below the navbar, and its collapse tab still sits on the sidebar's right edge and still toggles.
3. The map fills the remaining height with no vertical page scrollbar.
4. On mobile the filter bottom sheet still opens, and the brand is visible in the navbar.
5. Switching CA/ES/EN from the navbar still re-labels the UI.
