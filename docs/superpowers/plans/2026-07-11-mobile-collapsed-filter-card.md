# Mobile Collapsed Filter Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the collapsed mobile card state what filters are applied and which colour on the map is which restriction overlay.

**Architecture:** Three changes, each independently shippable. The card drops its dead `Highline Scout` title row and shows a label-free applied-filter summary built from a new i18n template. A new presentational `RestrictionLegend` component maps enabled layer ids to swatch + label. `App` wires the legend into `MobileControlSheet` as a ReactNode prop, matching the component's existing `filters` / `statuses` / `restrictions` prop pattern.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind, shadcn/Radix UI, Vitest + Testing Library, custom `useI18n` hook.

## Global Constraints

- Run all frontend commands from `frontend/`. Test command is `npm test` (`vitest run`); a single file is `npm test -- src/path/File.test.tsx`.
- `i18n.test.tsx` enforces **catalog parity**: any new key in `STRINGS.ca` MUST also exist in `STRINGS.es` and `STRINGS.en`, or the suite fails.
- Tests run under jsdom, where `navigator.language` is `en-US`, so `I18nProvider` resolves to **English**. Assert against English strings.
- `RESTRICTION_STRINGS` only has `es` and `ca` entries. Under `en`, `restrictionText(id, lang, layer)` falls back to the `layer.label` supplied by the API. Test fixtures must therefore assert the fixture's own `label`.
- `AppShell` renders the desktop sidebar **and** the mobile controls into the DOM at the same time (only CSS hides one). Anything rendered in both appears twice — always scope queries with `within(...)`. The legend is rendered only inside `MobileControlSheet`, so it stays unique.
- The summary string uses an en dash (`–`), a middle dot (`·`) and `≥`. Copy these characters exactly.
- Do not touch `DesktopSidebar` or the contents of the sheet. `RestrictionLayerControls` keeps its full labels, checkboxes and tooltips.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/lib/i18n/strings.ts` | Modify: add the `filterSummary` template to all three catalogs. |
| `frontend/src/components/MobileControlSheet.tsx` | Modify: restructure the collapsed card — drop the title, add the `legend` slot. |
| `frontend/src/components/RestrictionLegend.tsx` | Create: presentational swatch + label list for enabled layers. |
| `frontend/src/components/RestrictionLegend.test.tsx` | Create: unit tests for the legend. |
| `frontend/src/App.tsx` | Modify: build the summary from the new key, render and pass the legend. |
| `frontend/src/App.mobile.test.tsx` | Modify: integration tests for the collapsed card. |

---

## Task 1: Applied-filter summary on a title-free card

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (add one key to each of the three catalogs)
- Modify: `frontend/src/components/MobileControlSheet.tsx:22-36` (the collapsed card block)
- Modify: `frontend/src/App.tsx:110-114` (the `summary` useMemo)
- Test: `frontend/src/App.mobile.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a `data-testid="mobile-summary-card"` attribute on the collapsed card's root `<div>`, which Task 3's test scopes its queries to. The `MobileControlSheetProps.summary: string` prop keeps its name and type.

- [ ] **Step 1: Write the failing test**

Add this test to the existing `describe("mobile control sheet", ...)` block in `frontend/src/App.mobile.test.tsx`. Leave the existing mocks and the existing test alone.

```tsx
  it("summarises the applied filters, not the drafts", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));

    const card = screen.getByTestId("mobile-summary-card");
    expect(within(card).getByText("20–150 m · exp ≥30 m")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /open controls/i }));
    const sheet = await screen.findByRole("dialog");
    const sliders = within(sheet).getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    // Dragging a slider is only a draft — the card must still describe the map.
    expect(within(card).getByText("20–150 m · exp ≥30 m")).toBeInTheDocument();

    await user.click(within(sheet).getByRole("button", { name: /apply filters/i }));

    await waitFor(() =>
      expect(within(card).getByText("21–150 m · exp ≥30 m")).toBeInTheDocument(),
    );
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: FAIL — `Unable to find an element by: [data-testid="mobile-summary-card"]`.

- [ ] **Step 3: Add the `filterSummary` key to all three catalogs**

In `frontend/src/lib/i18n/strings.ts`, add the key to each of `ca`, `es` and `en`, next to the existing `applyFilters` key. The three strings are identical today — `exp` abbreviates *exposició* / *exposición* / *exposure* alike — but each language owns its entry so any can be reworded independently.

```ts
    filterSummary: "{min}–{max} m · exp ≥{exp} m",
```

- [ ] **Step 4: Build the summary from the new key**

In `frontend/src/App.tsx`, replace the `summary` useMemo (currently at lines 110-114):

```tsx
  const summary = useMemo(
    () =>
      t("filterSummary", {
        min: appliedLengthRange[0],
        max: appliedLengthRange[1],
        exp: appliedMinExposure,
      }),
    [t, appliedLengthRange, appliedMinExposure],
  );
```

- [ ] **Step 5: Restructure the collapsed card**

In `frontend/src/components/MobileControlSheet.tsx`, replace the fixed card `<div>` (currently lines 22-36) with:

```tsx
      <div
        data-testid="mobile-summary-card"
        className="fixed inset-x-3 bottom-3 z-[1100] rounded-xl border bg-card/95 p-3 shadow-xl backdrop-blur"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-border" />
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1 text-sm font-medium">{props.summary}</div>
          <SheetTrigger asChild>
            <Button type="button" size="sm" aria-label={t("openControls")}>
              <SlidersHorizontal className="mr-2 h-4 w-4" />
              {t("filters")}
            </Button>
          </SheetTrigger>
        </div>
      </div>
```

The `Highline Scout` title and both `truncate` classes are gone: the summary is now short enough to fit, and truncation is what hid the numbers in the first place.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm test`
Expected: PASS — all suites, including the catalog-parity test that now sees `filterSummary` in all three languages.

- [ ] **Step 7: Typecheck**

Run: `npm run build`
Expected: exit 0, no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/components/MobileControlSheet.tsx frontend/src/App.tsx frontend/src/App.mobile.test.tsx
git commit -m "feat(web): summarise the applied filters on the collapsed mobile card"
```

---

## Task 2: The RestrictionLegend component

**Files:**
- Create: `frontend/src/components/RestrictionLegend.tsx`
- Test: `frontend/src/components/RestrictionLegend.test.tsx`

**Interfaces:**
- Consumes: `RestrictionLayerMeta` from `@/types/highliner` (`{ id, label, tooltip, highlight, color }`), and `restrictionText(id, lang, fallback)` from `@/lib/i18n`.
- Produces: `RestrictionLegend({ layers, enabled }: { layers: RestrictionLayerMeta[]; enabled: string[] })`, a named export returning `null` when no enabled layer has metadata. Task 3 renders it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/RestrictionLegend.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { RestrictionLegend } from "./RestrictionLegend";

const layers: RestrictionLayerMeta[] = [
  { id: "zepa", label: "ZEPA (Aves)", tooltip: "", highlight: "", color: "#e31a1c" },
  { id: "zec", label: "ZEC / LIC", tooltip: "", highlight: "", color: "#ff7f00" },
  { id: "enp", label: "Espacios Naturales Protegidos", tooltip: "", highlight: "", color: "#6a3d9a" },
];

function renderLegend(enabled: string[]) {
  return render(
    <I18nProvider>
      <RestrictionLegend layers={layers} enabled={enabled} />
    </I18nProvider>,
  );
}

describe("RestrictionLegend", () => {
  it("renders nothing when no layer is enabled", () => {
    const { container } = renderLegend([]);

    expect(container).toBeEmptyDOMElement();
  });

  it("names and colours every enabled layer", () => {
    renderLegend(["zepa", "enp"]);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("ZEPA (Aves)");
    expect(items[0].querySelector("span[aria-hidden]")).toHaveStyle({
      backgroundColor: "#e31a1c",
    });
    expect(items[1]).toHaveTextContent("Espacios Naturales Protegidos");
    expect(items[1].querySelector("span[aria-hidden]")).toHaveStyle({
      backgroundColor: "#6a3d9a",
    });
  });

  it("orders the legend by the layer list, not by the order they were enabled", () => {
    renderLegend(["enp", "zepa"]);

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("ZEPA (Aves)");
    expect(items[1]).toHaveTextContent("Espacios Naturales Protegidos");
  });

  it("ignores an enabled id that has no layer metadata", () => {
    renderLegend(["ghost", "zepa"]);

    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/RestrictionLegend.test.tsx`
Expected: FAIL — cannot resolve `./RestrictionLegend`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/RestrictionLegend.tsx`:

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
    <ul aria-label={t("restrictions")} className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
      {visible.map((layer) => (
        <li key={layer.id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 rounded-sm border"
            style={{ backgroundColor: layer.color }}
          />
          {restrictionText(layer.id, lang, layer).label}
        </li>
      ))}
    </ul>
  );
}
```

Filtering `layers` by `enabled` — rather than mapping over `enabled` — is what gives the stable order and drops unknown ids for free.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/components/RestrictionLegend.test.tsx`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RestrictionLegend.tsx frontend/src/components/RestrictionLegend.test.tsx
git commit -m "feat(web): add a restriction legend component"
```

---

## Task 3: Wire the legend into the collapsed card

**Files:**
- Modify: `frontend/src/components/MobileControlSheet.tsx` (props + card body)
- Modify: `frontend/src/App.tsx` (render `RestrictionLegend`, pass it down)
- Test: `frontend/src/App.mobile.test.tsx`

**Interfaces:**
- Consumes: `RestrictionLegend` from Task 2; `data-testid="mobile-summary-card"` from Task 1.
- Produces: a new `legend: ReactNode` field on `MobileControlSheetProps`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/App.mobile.test.tsx`, first replace the `./lib/api` mock so the app has a layer to legend. It currently resolves to `[]`:

```tsx
vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: vi.fn().mockResolvedValue([
    { id: "zepa", label: "ZEPA (Aves)", tooltip: "tooltip", highlight: "highlight", color: "#e31a1c" },
  ]),
}));
```

Then add this test to the `describe("mobile control sheet", ...)` block:

```tsx
  it("legends the restriction layers drawn on the map", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));

    const card = screen.getByTestId("mobile-summary-card");
    expect(within(card).queryByText("ZEPA (Aves)")).toBeNull();

    await user.click(screen.getByRole("button", { name: /open controls/i }));
    const sheet = await screen.findByRole("dialog");
    await user.click(await within(sheet).findByRole("checkbox", { name: /ZEPA/ }));

    expect(within(card).getByText("ZEPA (Aves)")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: FAIL — the last assertion finds no `ZEPA (Aves)` inside the card (the label exists only inside the sheet's checkbox list).

- [ ] **Step 3: Add the `legend` slot to the sheet**

In `frontend/src/components/MobileControlSheet.tsx`, add the prop to the interface:

```tsx
interface MobileControlSheetProps {
  summary: string;
  legend: ReactNode;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

Then render it inside the collapsed card, directly after the summary row's closing `</div>` and before the card's own closing `</div>`:

```tsx
        {props.legend}
```

The legend owns its `mt-2` spacing and collapses to `null` when nothing is enabled, so the card needs no conditional wrapper.

- [ ] **Step 4: Render and pass the legend from App**

In `frontend/src/App.tsx`, add the import:

```tsx
import { RestrictionLegend } from "./components/RestrictionLegend";
```

Add the node next to the existing `restrictions` node:

```tsx
  const legend = <RestrictionLegend layers={restrictionLayers} enabled={enabledRestrictions} />;
```

And pass it in the `MobileControlSheet` element:

```tsx
          <MobileControlSheet
            summary={summary}
            legend={legend}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
            open={sheetOpen}
            onOpenChange={setSheetOpen}
          />
```

- [ ] **Step 5: Run the full suite**

Run: `npm test`
Expected: PASS — all suites.

- [ ] **Step 6: Typecheck**

Run: `npm run build`
Expected: exit 0, no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/MobileControlSheet.tsx frontend/src/App.tsx frontend/src/App.mobile.test.tsx
git commit -m "feat(web): legend the visible restriction layers on the collapsed mobile card"
```

---

## Verification

After Task 3, drive the real app rather than trusting the suite. Run `npm run dev`, open the app at a mobile viewport (~390px wide), and confirm:

- The card is **one row** on load — no title, summary reads `20–150 m · exp ≥30 m`, nothing clipped.
- Open the sheet, drag the length slider: the card behind it does not change until `Apply filters` is pressed.
- Tick all three restriction layers: the legend row appears, wraps onto a second line for `Espais Naturals Protegits`, and each swatch matches the polygon colour drawn on the map.
- Untick them all: the legend row disappears and the card returns to one row.
