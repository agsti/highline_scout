# Nav, Sidebar & Filter Card Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the app chrome around the map (top navbar + desktop sidebar + mobile summary card) with floating pills and panels, per `design/design_handoff_nav_redesign/README.md` (options 2a mobile, 3a density, 1d desktop).

**Architecture:** The map goes full-bleed. `AppShell` becomes a positioning root that renders the map and a `chrome` slot; `MapChrome` composes the floating pieces (nav, desktop filters panel, mobile bottom stack, caveat chip). Density mode is lifted out of `MapView` via an `onDensityModeChange` callback so the chrome can own the meter chip and zoom hint. Zoom controls become React buttons inside `MapView` (Leaflet's built-in control is disabled).

**Tech Stack:** React 18 + TypeScript + Tailwind 3 + shadcn/ui (Radix) + Leaflet + lucide-react; Vitest + Testing Library.

## Global Constraints

- All values are expressed through Tailwind theme tokens where one exists (`bg-primary`, `text-muted-foreground`, …); new tokens are added to `globals.css` + `tailwind.config.ts` rather than hard-coded hex in components.
- Breakpoint `md` (768px) switches mobile ↔ desktop chrome. Both variants may be mounted in the DOM; visibility is Tailwind-only (`md:hidden` / `hidden md:block`). Tests must therefore scope queries when a component is rendered twice.
- Floating surfaces sit above Leaflet panes: `z-[1000]`; dialogs/sheets keep `z-[1200]`.
- Copy lives in `src/lib/i18n/strings.ts` for all three languages (ca, es, en). No literal user-facing text in components except the "Highline Scout" wordmark.
- Logo mark stays the "HS" placeholder (decision: do not use `assets/highline-compass.png` yet).
- The account / "Entrar" button is **omitted** (decision: no auth flow exists; no dead-end UI). Everything else in the spec ships.
- Run `npm test` (in `frontend/`) after each task; the whole suite must be green before commit.

---

### Task 1: Design tokens

**Files:**
- Modify: `frontend/src/styles/globals.css:8-29`
- Modify: `frontend/tailwind.config.ts:9-49`

- [ ] **Step 1: Add the new CSS variables**

In `globals.css`, inside `:root`, after `--radius: 0.45rem;`:

```css
    /* #114B45 — deep brand, used for wordmark and panel titles */
    --primary-deep: 174 63% 18%;
    /* #112B26 — dark floating surface (filter pill, zoom hint toast) */
    --ink: 168 43% 12%;
    /* #DCE7E0 / #E3ECE6 — hairlines, lighter than --border */
    --hairline: 142 19% 88%;
    --hairline-soft: 140 19% 91%;
```

- [ ] **Step 2: Expose them in the Tailwind theme**

In `tailwind.config.ts`, extend `colors`:

```ts
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          deep: "hsl(var(--primary-deep))",
        },
        ink: "hsl(var(--ink))",
        hairline: {
          DEFAULT: "hsl(var(--hairline))",
          soft: "hsl(var(--hairline-soft))",
        },
```

and add, next to `borderRadius`:

```ts
      boxShadow: {
        pill: "0 2px 10px rgba(22,48,42,0.14)",
        "pill-lg": "0 2px 12px rgba(22,48,42,0.16)",
        zoom: "0 2px 8px rgba(22,48,42,0.16)",
        panel: "0 8px 32px rgba(22,48,42,0.2)",
        "filter-pill": "0 8px 24px rgba(22,48,42,0.35)",
      },
```

- [ ] **Step 3: Verify the theme compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds (tokens are unused so far — this only proves the config parses).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/globals.css frontend/tailwind.config.ts
git commit -m "feat(web): add floating-chrome design tokens"
```

---

### Task 2: New i18n strings

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts`
- Test: `frontend/src/lib/i18n/i18n.test.tsx`

**Interfaces:**
- Produces: string keys `about`, `caveatShort`, `zoomIn`, `zoomOut`, `densityHint`, `close` — consumed by Tasks 4–7.

- [ ] **Step 1: Write the failing test**

Append to the `describe("catalog parity", …)` block in `i18n.test.tsx`:

```tsx
  it("carries the floating-chrome copy in every language", () => {
    expect(STRINGS.ca.caveatShort).toBe("Zones sense verificar — valora el terreny tu mateix");
    expect(STRINGS.es.caveatShort).toBe("Zonas sin verificar — valora el terreno tú mismo");
    expect(STRINGS.en.caveatShort).toBe("Unverified zones — assess the terrain yourself");

    expect(STRINGS.es.densityHint).toBe("Amplía para ver zonas");
    expect(STRINGS.en.about).toBe("About Highline Scout");
    expect(STRINGS.ca.zoomIn).toBe("Amplia");
  });
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/lib/i18n/i18n.test.tsx`
Expected: FAIL — TypeScript/property errors, `STRINGS.ca.caveatShort` is `undefined`.

- [ ] **Step 3: Add the keys to all three catalogs**

`ca` (insert after `caveat`):

```ts
    caveatShort: "Zones sense verificar — valora el terreny tu mateix",
    about: "Sobre Highline Scout",
    close: "Tanca",
    zoomIn: "Amplia",
    zoomOut: "Redueix",
    densityHint: "Amplia per veure zones",
```

`es`:

```ts
    caveatShort: "Zonas sin verificar — valora el terreno tú mismo",
    about: "Acerca de Highline Scout",
    close: "Cerrar",
    zoomIn: "Acercar",
    zoomOut: "Alejar",
    densityHint: "Amplía para ver zonas",
```

`en`:

```ts
    caveatShort: "Unverified zones — assess the terrain yourself",
    about: "About Highline Scout",
    close: "Close",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    densityHint: "Zoom in to see zones",
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/lib/i18n/i18n.test.tsx`
Expected: PASS (including the pre-existing key-parity test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/lib/i18n/i18n.test.tsx
git commit -m "feat(web): add copy for the floating chrome"
```

---

### Task 3: LanguageSwitcher becomes a segmented control

**Files:**
- Modify: `frontend/src/components/LanguageSwitcher.tsx` (full rewrite — the flag `Select` goes away)
- Test: `frontend/src/components/LanguageSwitcher.test.tsx` (full rewrite)

**Interfaces:**
- Produces: `<LanguageSwitcher />` — a `role="group"` of three `aria-pressed` buttons (CA/ES/EN in `LANGS` order). No props. Still used by `SafetyDisclaimerDialog`.

- [ ] **Step 1: Write the failing test** — replace the whole body of `LanguageSwitcher.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

function renderSwitcher() {
  return render(
    <I18nProvider>
      <LanguageSwitcher />
    </I18nProvider>,
  );
}

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    window.localStorage.setItem("lang", "ca");
  });

  it("shows every language as a segment and presses the active one", () => {
    renderSwitcher();

    const group = screen.getByRole("group", { name: "Idioma" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Català" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches language when a segment is clicked", async () => {
    const user = userEvent.setup();
    renderSwitcher();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/components/LanguageSwitcher.test.tsx`
Expected: FAIL — no element with `role="group"` (the current switcher is a combobox).

- [ ] **Step 3: Rewrite the component**

```tsx
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const SHORT: Record<Lang, string> = { ca: "CA", es: "ES", en: "EN" };
const NAMES: Record<Lang, string> = { ca: "Català", es: "Español", en: "English" };

export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();

  return (
    <div role="group" aria-label={t("language")} className="flex items-center gap-0.5 pr-1">
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
              "rounded-full px-[9px] py-[7px] text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:px-[11px] md:py-2 md:text-xs",
              active
                ? "bg-primary font-bold text-primary-foreground"
                : "font-semibold text-muted-foreground hover:bg-accent",
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

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/LanguageSwitcher.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LanguageSwitcher.tsx frontend/src/components/LanguageSwitcher.test.tsx
git commit -m "feat(web): turn the language switcher into a segmented control"
```

---

### Task 4: Floating nav (brand pill + controls pill + About dialog)

**Files:**
- Create: `frontend/src/components/BrandPill.tsx`
- Create: `frontend/src/components/FloatingNav.tsx`
- Create: `frontend/src/components/AboutDialog.tsx`
- Create: `frontend/src/components/FloatingNav.test.tsx`
- Delete: `frontend/src/components/NavBar.tsx` (in Task 8, once `AppShell` stops importing it)

**Interfaces:**
- Produces: `<FloatingNav onAbout={() => void} />`, `<AboutDialog open={boolean} onOpenChange={(open: boolean) => void} />`, `<BrandPill />`.

- [ ] **Step 1: Write the failing test** (`FloatingNav.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FloatingNav } from "./FloatingNav";

function renderNav(onAbout = vi.fn()) {
  render(
    <I18nProvider>
      <FloatingNav onAbout={onAbout} />
    </I18nProvider>,
  );
  return onAbout;
}

describe("FloatingNav", () => {
  it("renders the brand, the language switcher, and the info button", () => {
    window.localStorage.setItem("lang", "en");
    renderNav();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Highline Scout" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About Highline Scout" })).toBeInTheDocument();
  });

  it("opens the about dialog from the info button", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("lang", "en");
    const onAbout = renderNav();

    await user.click(screen.getByRole("button", { name: "About Highline Scout" }));

    expect(onAbout).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/components/FloatingNav.test.tsx`
Expected: FAIL — cannot resolve `./FloatingNav`.

- [ ] **Step 3: Write `BrandPill.tsx`**

```tsx
export function BrandPill() {
  return (
    <div className="flex items-center gap-2 rounded-full bg-card/[0.94] py-[7px] pl-2 pr-3.5 shadow-pill backdrop-blur-[8px] md:py-2 md:pl-[9px] md:pr-4 md:shadow-pill-lg">
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-extrabold text-primary-foreground md:h-[26px] md:w-[26px]"
      >
        HS
      </span>
      <h1 className="text-[15px] font-bold tracking-[-0.01em] text-primary-deep md:text-base">
        Highline Scout
      </h1>
    </div>
  );
}
```

- [ ] **Step 4: Write `FloatingNav.tsx`**

```tsx
import { Info } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { BrandPill } from "./BrandPill";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface FloatingNavProps {
  onAbout: () => void;
}

export function FloatingNav({ onAbout }: FloatingNavProps) {
  const { t } = useI18n();

  return (
    <header className="pointer-events-none absolute inset-x-3 top-3.5 z-[1000] flex items-center justify-between gap-2 md:inset-x-4 md:top-4">
      <div className="pointer-events-auto">
        <BrandPill />
      </div>
      <div className="pointer-events-auto flex items-center gap-0.5 rounded-full bg-card/[0.94] p-1 shadow-pill backdrop-blur-[8px] md:shadow-pill-lg">
        <LanguageSwitcher />
        <span aria-hidden className="h-5 w-px shrink-0 bg-hairline md:h-[22px]" />
        <button
          type="button"
          aria-label={t("about")}
          onClick={onAbout}
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:h-9 md:w-9"
        >
          <Info className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 5: Write `AboutDialog.tsx`** — reuses the existing disclaimer copy plus the full caveat and the MITECO credit.

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
          <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
          <p>{t("disclaimerBody")}</p>
          <p>{t("disclaimerResponsibility")}</p>
          <p>{t("caveat")}</p>
          <p className="text-xs">{t("restrictionCredit")}</p>
          <p className="text-xs">{t("disclaimerPrivacy")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npx vitest run src/components/FloatingNav.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/BrandPill.tsx frontend/src/components/FloatingNav.tsx frontend/src/components/AboutDialog.tsx frontend/src/components/FloatingNav.test.tsx
git commit -m "feat(web): add the floating nav and about dialog"
```

---

### Task 5: MapView — custom zoom controls and density-mode callback

**Files:**
- Create: `frontend/src/components/map/ZoomControls.tsx`
- Modify: `frontend/src/components/map/MapView.tsx:89` (drop `showDensityLegend` state), `:174` (disable Leaflet zoom control), `:243` (call the callback), `:456-473` (delete the old legend), plus the props interface
- Test: `frontend/src/components/map/MapView.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks except tokens.
- Produces: `MapView` gains `onDensityModeChange?: (dense: boolean) => void`. The old in-map density legend is gone — `MapChrome` (Task 7) renders the meter instead.

- [ ] **Step 1: Write the failing test** — add to `MapView.test.tsx`. The existing `leafletMocks` object needs two more spies; add `zoomIn: vi.fn()` and `zoomOut: vi.fn()` to the `vi.hoisted` block and to the object returned by the mocked `L.map(...)` (same place `setView`/`on` are wired).

```tsx
  it("zooms the map from the floating zoom controls", async () => {
    const user = userEvent.setup();
    renderMap();

    await user.click(screen.getByRole("button", { name: /zoom in|acercar|amplia/i }));
    expect(leafletMocks.zoomIn).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: /zoom out|alejar|redueix/i }));
    expect(leafletMocks.zoomOut).toHaveBeenCalledTimes(1);
  });

  it("reports density mode to the parent instead of drawing its own legend", async () => {
    const onDensityModeChange = vi.fn();
    leafletState.zoom = 10; // <= DENSITY_MAX_ZOOM
    renderMap({ onDensityModeChange });

    await waitFor(() => expect(onDensityModeChange).toHaveBeenCalledWith(true));
    expect(screen.queryByText(/line chance|probabilitat|probabilidad/i)).toBeNull();
  });
```

Note: `renderMap` is the local helper already in this file — pass the extra prop through it (extend its props argument if it does not already spread overrides).

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/components/map/MapView.test.tsx`
Expected: FAIL — no zoom buttons, `onDensityModeChange` never called.

- [ ] **Step 3: Write `ZoomControls.tsx`**

```tsx
import { Minus, Plus } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
}

export function ZoomControls({ onZoomIn, onZoomOut }: ZoomControlsProps) {
  const { t } = useI18n();
  const button =
    "flex h-[38px] w-[38px] items-center justify-center text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:h-9 md:w-9";

  return (
    <div className="absolute left-3 top-[78px] z-[1000] flex flex-col overflow-hidden rounded-[10px] bg-card shadow-zoom md:bottom-10 md:left-auto md:right-4 md:top-auto">
      <button type="button" aria-label={t("zoomIn")} onClick={onZoomIn} className={button}>
        <Plus className="h-4 w-4" aria-hidden />
      </button>
      <span aria-hidden className="h-px bg-hairline" />
      <button type="button" aria-label={t("zoomOut")} onClick={onZoomOut} className={button}>
        <Minus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Wire it into `MapView.tsx`**

1. Add to `MapViewProps`: `onDensityModeChange?: (dense: boolean) => void;` and destructure it.
2. Delete `const [showDensityLegend, setShowDensityLegend] = useState(false);`.
3. In the map init effect, disable the built-in control:
   ```ts
   const map = L.map(elRef.current, { zoomControl: false }).setView(view.center, view.zoom);
   ```
4. In `load()`, replace `setShowDensityLegend(densityMode);` with `onDensityModeChange?.(densityMode);` and add `onDensityModeChange` to that effect's dependency array.
5. Delete the whole `{showDensityLegend ? (…) : null}` block at the end of the JSX, and drop the now-unused `tealShade` import.
6. Render the controls as the last child of the root `<div className="relative h-full w-full">`:
   ```tsx
   <ZoomControls
     onZoomIn={() => mapRef.current?.zoomIn()}
     onZoomOut={() => mapRef.current?.zoomOut()}
   />
   ```
   with `import { ZoomControls } from "./ZoomControls";`.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npx vitest run src/components/map`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/map/ZoomControls.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "feat(web): float the zoom controls and lift density mode out of the map"
```

---

### Task 6: Mobile bottom chrome (filter pill, legend chip, meter, zoom hint)

**Files:**
- Create: `frontend/src/components/FilterPill.tsx`
- Create: `frontend/src/components/LineChanceMeter.tsx`
- Create: `frontend/src/components/ZoomHintToast.tsx`
- Create: `frontend/src/components/CaveatChip.tsx`
- Modify: `frontend/src/components/RestrictionLegend.tsx` (restyle as a chip)
- Modify: `frontend/src/components/MobileControlSheet.tsx` (drop the summary card; sheet only)
- Test: `frontend/src/components/FilterPill.test.tsx`, `frontend/src/components/RestrictionLegend.test.tsx` (existing — must stay green)

**Interfaces:**
- Produces:
  - `<FilterPill summary={string} onClick={() => void} />` — `data-testid="filter-pill"`, `aria-label={t("openControls")}`
  - `<LineChanceMeter />` — `data-testid="line-chance-meter"`
  - `<ZoomHintToast active={boolean} />` plus `export const ZOOM_HINT_MS = 4000`
  - `<CaveatChip />`
  - `<MobileControlSheet filters restrictions statuses caveat open onOpenChange />` — **the `summary` and `legend` props are removed.**

- [ ] **Step 1: Write the failing test** (`FilterPill.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FilterPill } from "./FilterPill";

describe("FilterPill", () => {
  it("shows the applied summary and opens the sheet when tapped", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    window.localStorage.setItem("lang", "en");

    render(
      <I18nProvider>
        <FilterPill summary="20–150 m · exp ≥30 m" onClick={onClick} />
      </I18nProvider>,
    );

    const pill = screen.getByTestId("filter-pill");
    expect(pill).toHaveTextContent("Filters");
    expect(pill).toHaveTextContent("20–150 m · exp ≥30 m");

    await user.click(screen.getByRole("button", { name: "Open controls" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/components/FilterPill.test.tsx`
Expected: FAIL — cannot resolve `./FilterPill`.

- [ ] **Step 3: Write `FilterPill.tsx`**

```tsx
import { SlidersHorizontal } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface FilterPillProps {
  summary: string;
  onClick: () => void;
}

export function FilterPill({ summary, onClick }: FilterPillProps) {
  const { t } = useI18n();

  return (
    <button
      type="button"
      data-testid="filter-pill"
      aria-label={t("openControls")}
      onClick={onClick}
      className="pointer-events-auto flex min-h-[44px] items-center gap-2.5 whitespace-nowrap rounded-full bg-ink/[0.94] px-5 py-[13px] text-primary-foreground shadow-filter-pill backdrop-blur-[8px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden />
      <span className="text-sm font-bold">{t("filters")}</span>
      <span aria-hidden className="h-4 w-px shrink-0 bg-white/25" />
      <span className="text-[13px] font-medium opacity-[0.85]">{summary}</span>
    </button>
  );
}
```

- [ ] **Step 4: Write `LineChanceMeter.tsx`** — the gradient is the real `tealShade` ramp from `map-style`, sampled low→high.

```tsx
import { useI18n } from "@/lib/i18n";
import { tealShade } from "@/lib/map-style";

const RAMP = `linear-gradient(to right, ${tealShade(0)}, ${tealShade(0.45)}, ${tealShade(0.75)}, ${tealShade(1)})`;

export function LineChanceMeter() {
  const { t } = useI18n();

  return (
    <div
      data-testid="line-chance-meter"
      className="pointer-events-auto flex items-center gap-2.5 whitespace-nowrap rounded-full bg-card/95 px-3.5 py-[7px] shadow-pill backdrop-blur-[8px]"
    >
      <span className="text-[11px] font-bold text-primary-deep">{t("lineDensity")}</span>
      <span className="flex items-center gap-1.5">
        <span className="text-[10px] text-muted-foreground">{t("sparse")}</span>
        <span
          aria-hidden
          className="h-2 w-[84px] rounded border border-foreground/10"
          style={{ backgroundImage: RAMP }}
        />
        <span className="text-[10px] text-muted-foreground">{t("dense")}</span>
      </span>
    </div>
  );
}
```

- [ ] **Step 5: Write `ZoomHintToast.tsx`** — transient, re-shows every time density mode is entered.

```tsx
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";

export const ZOOM_HINT_MS = 4000;

export function ZoomHintToast({ active }: { active: boolean }) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!active) {
      setVisible(false);
      return;
    }
    setVisible(true);
    const timeout = window.setTimeout(() => setVisible(false), ZOOM_HINT_MS);
    return () => window.clearTimeout(timeout);
  }, [active]);

  if (!visible) return null;

  return (
    <div
      role="status"
      className="pointer-events-none absolute left-1/2 top-[78px] z-[1000] -translate-x-1/2 whitespace-nowrap rounded-full bg-ink/85 px-[13px] py-1.5 text-[11px] font-semibold text-primary-foreground md:hidden"
    >
      {t("densityHint")}
    </div>
  );
}
```

- [ ] **Step 6: Write `CaveatChip.tsx`** (desktop-only surface, lives here because it belongs to the chrome family)

```tsx
import { TriangleAlert } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function CaveatChip() {
  const { t } = useI18n();

  return (
    <div className="absolute bottom-3 left-4 z-[1000] hidden items-center gap-2 rounded-full bg-card/[0.92] px-3.5 py-1.5 shadow-pill md:flex">
      <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      <span className="text-[11px] font-semibold text-destructive">{t("caveatShort")}</span>
    </div>
  );
}
```

- [ ] **Step 7: Restyle `RestrictionLegend.tsx` as a detached chip** (keep the `<ul>`/`<li>` structure — `RestrictionLegend.test.tsx` asserts on list items and swatch colors)

```tsx
import { restrictionText, useI18n } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";

interface RestrictionLegendProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
}

export function RestrictionLegend({ layers, enabled }: RestrictionLegendProps) {
  const { lang, t } = useI18n();
  const visible = layers.filter((layer) => enabled.includes(layer.id));

  if (visible.length === 0) return null;

  return (
    <ul
      aria-label={t("restrictions")}
      data-testid="legend-chip"
      className="pointer-events-auto flex items-center gap-3 rounded-full bg-card/[0.92] px-3.5 py-1.5 shadow-pill backdrop-blur-[8px]"
    >
      {visible.map((layer) => (
        <li
          key={layer.id}
          className="flex items-center gap-1.5 whitespace-nowrap text-[11px] text-muted-foreground"
        >
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: layer.color }}
          />
          {restrictionText(layer.id, lang, layer).label}
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 8: Slim `MobileControlSheet.tsx` down to the sheet itself**

```tsx
import type { ReactNode } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";

interface MobileControlSheetProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MobileControlSheet(props: MobileControlSheetProps) {
  const { t } = useI18n();

  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent
        side="bottom"
        closeLabel={t("closeControls")}
        className="max-h-[88dvh] overflow-y-auto rounded-t-2xl"
      >
        <SheetHeader>
          <SheetTitle>{t("filters")}</SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-5">
          {props.filters}
          {props.statuses}
          {props.restrictions}
          <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
            {props.caveat}
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 9: Run the tests**

Run: `cd frontend && npx vitest run src/components/FilterPill.test.tsx src/components/RestrictionLegend.test.tsx`
Expected: PASS both.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/FilterPill.tsx frontend/src/components/LineChanceMeter.tsx frontend/src/components/ZoomHintToast.tsx frontend/src/components/CaveatChip.tsx frontend/src/components/RestrictionLegend.tsx frontend/src/components/MobileControlSheet.tsx frontend/src/components/FilterPill.test.tsx
git commit -m "feat(web): add the mobile filter pill, legend chip, meter and caveat chip"
```

---

### Task 7: Desktop floating filters panel

**Files:**
- Create: `frontend/src/components/FiltersPanel.tsx`
- Create: `frontend/src/components/FiltersPanel.test.tsx`
- Modify: `frontend/src/components/FilterControls.tsx` (desktop type scale)
- Modify: `frontend/src/components/ui/slider.tsx` (5px rail + 15px thumbs on `md`)
- Modify: `frontend/src/components/RestrictionLayerControls.tsx` (borderless inside the panel)

**Interfaces:**
- Consumes: `FilterControls`, `RestrictionLayerControls`, `StatusLine` (as ready-made `ReactNode`s passed by `App`).
- Produces: `<FiltersPanel filters restrictions statuses swatches />` where `swatches: string[]` is the list of enabled layer colors. Collapse state (`collapsed`, `restrictionsExpanded`) is **local** to the panel — no App state is needed since nothing else reads it.
- Both collapsible sections stay mounted and animate via `grid-template-rows` (200 ms), so filter controls remain queryable/tabbable and the App-level tests keep working.

- [ ] **Step 1: Write the failing test** (`FiltersPanel.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FiltersPanel } from "./FiltersPanel";

function renderPanel() {
  window.localStorage.setItem("lang", "en");
  render(
    <I18nProvider>
      <FiltersPanel
        filters={<div>panel filters</div>}
        restrictions={<div>panel restrictions</div>}
        statuses={<div>panel statuses</div>}
        swatches={["#e31a1c"]}
      />
    </I18nProvider>,
  );
}

describe("FiltersPanel", () => {
  it("renders the filter form and collapses to the header", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByText("panel filters")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Minimize panel" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Expand panel" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("discloses the restriction layers from the footer row", async () => {
    const user = userEvent.setup();
    renderPanel();

    const disclosure = screen.getByRole("button", { name: /restrictions/i });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");

    await user.click(disclosure);

    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("panel restrictions")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run src/components/FiltersPanel.test.tsx`
Expected: FAIL — cannot resolve `./FiltersPanel`.

- [ ] **Step 3: Write `FiltersPanel.tsx`**

```tsx
import { ChevronDown, ChevronRight, SlidersHorizontal } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface FiltersPanelProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  swatches: string[];
}

export function FiltersPanel({ filters, restrictions, statuses, swatches }: FiltersPanelProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);
  const [restrictionsExpanded, setRestrictionsExpanded] = useState(false);

  return (
    <div className="absolute left-4 top-[76px] z-[1000] hidden w-[296px] overflow-hidden rounded-[14px] bg-card/[0.97] shadow-panel backdrop-blur-[10px] md:block">
      <div className="flex items-center justify-between border-b border-hairline-soft px-3.5 py-[13px]">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-[15px] w-[15px] text-primary-deep" aria-hidden />
          <span className="text-[13px] font-bold text-primary-deep">{t("filters")}</span>
        </div>
        <button
          type="button"
          aria-label={collapsed ? t("panelExpand") : t("panelMinimize")}
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
          className="flex h-[26px] w-[26px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <ChevronDown
            className={cn("h-3 w-3 transition-transform duration-200", collapsed && "-rotate-90")}
            aria-hidden
          />
        </button>
      </div>

      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          collapsed ? "grid-rows-[0fr]" : "grid-rows-[1fr]",
        )}
      >
        <div className="overflow-hidden">
          <div className="flex flex-col gap-3.5 p-3.5">
            {filters}
            {statuses}
          </div>
          <div className="border-t border-hairline-soft">
            <button
              type="button"
              aria-expanded={restrictionsExpanded}
              onClick={() => setRestrictionsExpanded((value) => !value)}
              className="flex w-full items-center justify-between px-3.5 py-[11px] transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <span className="text-[13px] font-bold text-primary-deep">{t("restrictions")}</span>
              <span className="flex items-center gap-2">
                {swatches.map((color) => (
                  <span
                    key={color}
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: color }}
                  />
                ))}
                <ChevronRight
                  className={cn(
                    "h-2.5 w-2.5 text-muted-foreground transition-transform duration-200",
                    restrictionsExpanded && "rotate-90",
                  )}
                  aria-hidden
                />
              </span>
            </button>
            <div
              className={cn(
                "grid transition-[grid-template-rows] duration-200 ease-out",
                restrictionsExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
              )}
            >
              <div className="overflow-hidden">
                <div className="px-3.5 pb-3.5">{restrictions}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Tune the shared form primitives for the panel's type scale**

`ui/slider.tsx` — rail and thumbs (mobile sheet keeps the bigger touch target, `md` gets the spec's 5px/15px):

```tsx
      <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-hairline md:h-[5px]">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      {Array.from({ length: thumbCount }, (_, index) => (
        <SliderPrimitive.Thumb
          key={index}
          className="block h-5 w-5 rounded-full border-2 border-primary bg-background shadow-[0_1px_3px_rgba(22,48,42,0.2)] ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 md:h-[15px] md:w-[15px]"
        />
      ))}
```

`FilterControls.tsx` — 12px labels / 13px controls on `md`, and the panel's 36px apply button. Change only these class strings:

- both label rows: `className="flex items-center justify-between text-sm md:text-xs"`
- the `<Label>` inside them: `<Label className="md:font-semibold">`
- the anchors row: `className="flex items-center gap-2 text-sm md:text-[13px]"`
- the submit button: `<Button type="submit" className="w-full md:h-9 md:rounded-lg md:text-[13px] md:font-bold" disabled={!props.canApply}>`

`RestrictionLayerControls.tsx` — inside the panel the fieldset border double-frames the disclosure, so drop it:

- `<fieldset className="space-y-3">` (was `space-y-3 rounded-md border p-3`)
- `<legend className="sr-only">{t("restrictions")}</legend>` (the panel/sheet already titles the section)

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npx vitest run src/components/FiltersPanel.test.tsx src/components/FilterControls.test.tsx src/components/RestrictionLayerControls.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/FiltersPanel.tsx frontend/src/components/FiltersPanel.test.tsx frontend/src/components/FilterControls.tsx frontend/src/components/RestrictionLayerControls.tsx frontend/src/components/ui/slider.tsx
git commit -m "feat(web): add the desktop floating filters panel"
```

---

### Task 8: Compose the chrome — AppShell, MapChrome, App wiring

**Files:**
- Create: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/components/AppShell.tsx` (full rewrite)
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/components/DesktopSidebar.tsx`, `frontend/src/components/NavBar.tsx`
- Test: `frontend/src/components/AppShell.test.tsx` (rewrite), `frontend/src/App.test.tsx`, `frontend/src/App.mobile.test.tsx`

**Interfaces:**
- Consumes: `FloatingNav`, `AboutDialog`, `FiltersPanel`, `FilterPill`, `LineChanceMeter`, `ZoomHintToast`, `CaveatChip`, `RestrictionLegend`, `MobileControlSheet`, `MapView`.
- Produces:
  - `<AppShell map={ReactNode} chrome={ReactNode} />`
  - `<MapChrome summary legend filters restrictions statuses swatches densityMode sheetOpen onSheetOpenChange onAbout />`

- [ ] **Step 1: Write `MapChrome.tsx`**

```tsx
import type { ReactNode } from "react";
import { CaveatChip } from "./CaveatChip";
import { FilterPill } from "./FilterPill";
import { FiltersPanel } from "./FiltersPanel";
import { FloatingNav } from "./FloatingNav";
import { LineChanceMeter } from "./LineChanceMeter";
import { MobileControlSheet } from "./MobileControlSheet";
import { ZoomHintToast } from "./ZoomHintToast";

interface MapChromeProps {
  summary: string;
  caveat: string;
  legend: ReactNode;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  swatches: string[];
  densityMode: boolean;
  sheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
  onAbout: () => void;
}

export function MapChrome(props: MapChromeProps) {
  return (
    <>
      <FloatingNav onAbout={props.onAbout} />
      <FiltersPanel
        filters={props.filters}
        restrictions={props.restrictions}
        statuses={props.statuses}
        swatches={props.swatches}
      />
      <CaveatChip />
      <ZoomHintToast active={props.densityMode} />

      {props.densityMode ? (
        <div className="pointer-events-none absolute bottom-3 left-1/2 z-[1000] hidden -translate-x-1/2 md:block">
          <LineChanceMeter />
        </div>
      ) : null}

      <div className="pointer-events-none absolute inset-x-3 bottom-6 z-[1000] flex flex-col items-center gap-2 md:hidden">
        {props.legend}
        {props.densityMode ? <LineChanceMeter /> : null}
        <div className="mt-2">
          <FilterPill summary={props.summary} onClick={() => props.onSheetOpenChange(true)} />
        </div>
      </div>

      <MobileControlSheet
        filters={props.filters}
        restrictions={props.restrictions}
        statuses={props.statuses}
        caveat={props.caveat}
        open={props.sheetOpen}
        onOpenChange={props.onSheetOpenChange}
      />
    </>
  );
}
```

The 8px `gap-2` plus the pill's `mt-2` put the chip stack's bottom edge at 84px (24 bottom + 44 pill + 16), exactly as specced; when the meter is present it takes the 84px slot and the legend stacks 8px above it.

- [ ] **Step 2: Rewrite `AppShell.tsx`**

```tsx
import type { ReactNode } from "react";

interface AppShellProps {
  map: ReactNode;
  chrome: ReactNode;
}

export function AppShell({ map, chrome }: AppShellProps) {
  return (
    <div className="relative h-dvh overflow-hidden bg-background text-foreground">
      <main className="absolute inset-0">{map}</main>
      {chrome}
    </div>
  );
}
```

- [ ] **Step 3: Delete the dead components**

```bash
git rm frontend/src/components/DesktopSidebar.tsx frontend/src/components/NavBar.tsx
```

- [ ] **Step 4: Wire `App.tsx`**

Changes only (everything else stays):

1. Imports: drop `DesktopSidebar`, add `AboutDialog`, `MapChrome`.
2. New state:
   ```tsx
   const [densityMode, setDensityMode] = useState(false);
   const [aboutOpen, setAboutOpen] = useState(false);
   ```
3. New derived value next to `legend`:
   ```tsx
   const swatches = useMemo(
     () =>
       restrictionLayers
         .filter((layer) => enabledRestrictions.includes(layer.id))
         .map((layer) => layer.color),
     [restrictionLayers, enabledRestrictions],
   );
   ```
4. Render:
   ```tsx
   return (
     <>
       <AppShell
         map={
           <MapView
             minLen={appliedLengthRange[0]}
             maxLen={appliedLengthRange[1]}
             minExposure={appliedMinExposure}
             showAnchors={showAnchors}
             enabledRestrictions={enabledRestrictions}
             restrictionLayers={restrictionLayers}
             onViewportChange={handleViewportChange}
             onMapStatus={setMapStatus}
             onAnchorStatus={setAnchorStatus}
             onRestrictionStatus={setRestrictionStatus}
             onDensityModeChange={setDensityMode}
           />
         }
         chrome={
           <MapChrome
             summary={summary}
             caveat={t("caveat")}
             legend={legend}
             filters={filters}
             restrictions={restrictions}
             statuses={statuses}
             swatches={swatches}
             densityMode={densityMode}
             sheetOpen={sheetOpen}
             onSheetOpenChange={setSheetOpen}
             onAbout={() => setAboutOpen(true)}
           />
         }
       />
       <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
       <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
     </>
   );
   ```

- [ ] **Step 5: Rewrite `AppShell.test.tsx`**

Keep the localStorage/`document.lang` `beforeEach`/`afterEach` scaffolding verbatim; replace the `describe` body and the render helpers:

```tsx
function renderShell() {
  return render(
    <I18nProvider>
      <AppShell map={<div>map area</div>} chrome={<div>chrome</div>} />
    </I18nProvider>,
  );
}

// The sheet is controlled by App, so this stands in for that state.
function ControlledMobileControlSheet() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <FilterPill summary="20–150 m · exp ≥30 m" onClick={() => setOpen(true)} />
      <MobileControlSheet
        filters={<div>sheet filters</div>}
        statuses={<div>sheet status</div>}
        restrictions={<div>sheet restrictions</div>}
        caveat="Zones to scout"
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}

describe("AppShell", () => {
  it("renders the map and the chrome layer", () => {
    renderShell();
    expect(screen.getByText("map area")).toBeInTheDocument();
    expect(screen.getByText("chrome")).toBeInTheDocument();
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

  it("does not leave the document body non-interactive when the mobile sheet is closed", () => {
    render(
      <I18nProvider>
        <ControlledMobileControlSheet />
      </I18nProvider>,
    );

    expect(document.body.style.pointerEvents).toBe("");
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
});
```

Imports at the top become: `AppShell`, `FilterPill`, `MobileControlSheet`, `Dialog`/`DialogContent`, `I18nProvider`/`useI18n` (drop `DesktopSidebar`). The old "sidebar collapse" and "exactly one language switcher (combobox)" tests are deleted — the sidebar is gone and `FloatingNav.test.tsx` now owns nav assertions.

- [ ] **Step 6: Update `App.test.tsx` mocks**

Replace the `AppShell` / `DesktopSidebar` / `MobileControlSheet` mocks with:

```tsx
vi.mock("./components/AppShell", () => ({
  AppShell: ({ chrome, map }: { chrome: ReactNode; map: ReactNode }) => (
    <div>
      <div>{chrome}</div>
      <div>{map}</div>
    </div>
  ),
}));

vi.mock("./components/MapChrome", () => ({
  MapChrome: ({ filters, statuses, restrictions }: { filters: ReactNode; statuses: ReactNode; restrictions: ReactNode }) => (
    <div>
      {filters}
      {statuses}
      {restrictions}
    </div>
  ),
}));
```

and delete the `./components/DesktopSidebar` and `./components/MobileControlSheet` mocks.

Then fix the two tests that assumed the old duplicated chrome:

```tsx
  it("shows the map status in the chrome", async () => {
    renderApp();

    expect(await screen.findByText("3 zones")).toBeInTheDocument();
  });
```

and delete `it("does not show map actions in the mobile filter controls", …)` — the `actions` slot it guarded no longer exists on any component.

- [ ] **Step 7: Update `App.mobile.test.tsx`**

The summary card is gone: the pill carries the summary, and the legend is its own chip.

- In "summarises the applied filters, not the drafts": replace `screen.getByTestId("mobile-summary-card")` with `screen.getByTestId("filter-pill")` (keep the same `within(...)` text assertions).
- In "legends the restriction layers drawn on the map": replace the card lookups with
  ```tsx
  expect(screen.queryByTestId("legend-chip")).toBeNull();
  ```
  before enabling the layer, and after closing the sheet:
  ```tsx
  expect(within(screen.getByTestId("legend-chip")).getByText("ZEPA (Aves)")).toBeInTheDocument();
  ```
- In "expands the sheet when the card body is tapped" (rename to "opens the sheet from the filter pill"): click `within(screen.getByTestId("filter-pill")).getByText("20–150 m · exp ≥30 m")`.

- [ ] **Step 8: Run the full suite**

Run: `cd frontend && npm test`
Expected: PASS — all files, no unhandled errors.

- [ ] **Step 9: Typecheck and build**

Run: `cd frontend && npm run build`
Expected: `tsc -b` clean (this is what catches leftover imports of the deleted `DesktopSidebar`/`NavBar`), Vite build succeeds.

- [ ] **Step 10: Commit**

```bash
git add -A frontend/src
git commit -m "feat(web): full-bleed map with floating chrome"
```

---

### Task 9: Verify in the browser

**Files:** none (verification only)

- [ ] **Step 1: Run the app**

Run: `cd frontend && npm run dev` (serves on 127.0.0.1:5173)

- [ ] **Step 2: Check the mobile layout (390×800 viewport)**

- Brand pill top-left, controls pill top-right (CA/ES/EN + info), zoom stack under the nav at left.
- Dark "Filtros" pill bottom-center with the applied summary; tapping it opens the bottom sheet.
- Enable a restriction layer → legend chip appears above the pill.
- Zoom out past z12 → line-chance meter chip + transient "Amplía para ver zonas" toast.

- [ ] **Step 3: Check the desktop layout (≥1280px)**

- Full-bleed map, no sidebar and no collapse handle.
- Floating filters panel top-left (chevron collapses to the header; "Restricciones" row discloses the layers).
- Caveat chip bottom-left, zoom controls bottom-right, info dialog opens from the nav.

- [ ] **Step 4: Report** anything that deviates from `design/design_handoff_nav_redesign/README.md`.
