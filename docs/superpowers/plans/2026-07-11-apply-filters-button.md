# Apply Filters Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the length and exposure filters a draft that only reaches the map when the user presses an "Apply filters" button, sitting under the filters and above the restrictions.

**Architecture:** `App` holds two parallel sets of filter state — `draft*` (what the sliders edit) and `applied*` (what `MapView` queries with). Only `handleApply` copies draft into applied, so `MapView`'s existing fetch effect stops firing per drag frame with no change inside `MapView` itself. The button lives inside `FilterControls`, which becomes a `<form>` whose submit is the button; because both `DesktopSidebar` and `MobileControlSheet` render the same `filters` node, the button lands in the right place in both layouts with no layout plumbing.

**Tech Stack:** React 18 + TypeScript, Radix UI (shadcn-style wrappers in `src/components/ui/`), Tailwind, Vitest + React Testing Library, Leaflet (mocked in tests).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-apply-filters-button-design.md`.
- Working directory for all commands: `frontend/`.
- Test command: `npm test` (vitest run). Typecheck: `npx tsc -b`. Both must pass before any commit.
- Vitest does **not** typecheck; run `npx tsc -b` explicitly.
- The working tree already contains an uncommitted in-flight change (single `maxLen` slider → dual-thumb `lengthRange`). Build on it. Do **not** revert or "clean up" those files.
- Filter defaults, unchanged: length range `[20, 150]`, min exposure `30`.
- "Show anchors" is **not** deferred. It stays live.
- i18n: every new string goes in all three locales in `src/lib/i18n/strings.ts` — `ca`, `es`, `en` — or `tsc` fails (`StringKey` is derived from `STRINGS.ca`).
- In jsdom, `navigator.language` is `en-US`, so `I18nProvider` resolves to the **`en`** locale. Tests query by the English strings.
- Radix sliders do not respond to synthetic pointer drags in jsdom. Move them in tests by focusing the thumb and pressing an arrow key, e.g. `sliders[0].focus(); await user.keyboard("{ArrowRight}")` — this is the pattern already used in `src/App.analytics.test.tsx`.
- `AppShell` renders the desktop sidebar into the DOM at all times (it is hidden with CSS, which jsdom ignores), while `MobileControlSheet`'s content only mounts once the sheet is open. So with the sheet closed there are exactly 2 sliders and 1 Apply button; with it open there are 4 and 2. Scope mobile assertions with `within(screen.getByRole("dialog"))`.

---

### Task 1: Defer the search behind an Apply button

Makes the two sliders a draft, adds the submit button, and swaps the analytics event. This is one task because the `FilterControls` prop change, the `App` state split, and the analytics swap cannot compile or make sense apart from each other.

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (add `applyFilters` to `ca`, `es`, `en`)
- Modify: `frontend/src/components/FilterControls.tsx` (whole component)
- Modify: `frontend/src/App.tsx:22-24` (state), `:45-55` (commit handlers), `:71-82` (filters node), `:100-104` (summary), `:126-139` (MapView props)
- Create: `frontend/src/components/FilterControls.test.tsx`
- Create: `frontend/src/App.filters.test.tsx`
- Modify: `frontend/src/App.analytics.test.tsx:31-63` (replace the two `filter_changed` tests)

**Interfaces:**
- Consumes: `LengthRange` (`[min: number, max: number]`), already exported from `FilterControls.tsx`.
- Produces:
  - `FilterControlsProps` — `{ lengthRange: LengthRange; minExposure: number; showAnchors: boolean; canApply: boolean; onLengthRangeChange: (value: LengthRange) => void; onMinExposureChange: (value: number) => void; onShowAnchorsChange: (value: boolean) => void; onApply: () => void }`. `onLengthRangeCommit` and `onMinExposureCommit` are **removed**.
  - Analytics event `filters_applied` with properties `{ min_len: number; max_len: number; min_exposure: number }`. The `filter_changed` event is **removed**.
  - `App` exports nothing new; Task 2 relies on its `sheetOpen` state, added there.

- [ ] **Step 1: Add the i18n key**

In `frontend/src/lib/i18n/strings.ts`, add one line to each locale object, next to the existing `filters` key:

```ts
// in ca:
    applyFilters: "Aplica els filtres",
// in es:
    applyFilters: "Aplicar filtros",
// in en:
    applyFilters: "Apply filters",
```

- [ ] **Step 2: Write the failing FilterControls test**

Create `frontend/src/components/FilterControls.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { FilterControls, type LengthRange } from "./FilterControls";

function renderControls(overrides: Partial<ComponentProps<typeof FilterControls>> = {}) {
  const props = {
    lengthRange: [20, 150] as LengthRange,
    minExposure: 30,
    showAnchors: true,
    canApply: false,
    onLengthRangeChange: vi.fn(),
    onMinExposureChange: vi.fn(),
    onShowAnchorsChange: vi.fn(),
    onApply: vi.fn(),
    ...overrides,
  };
  render(
    <I18nProvider>
      <FilterControls {...props} />
    </I18nProvider>,
  );
  return props;
}

const applyButton = () => screen.getByRole("button", { name: /apply filters/i });

describe("FilterControls", () => {
  it("disables Apply when the draft matches what is on the map", () => {
    renderControls({ canApply: false });
    expect(applyButton()).toBeDisabled();
  });

  it("enables Apply once there is a pending change", () => {
    renderControls({ canApply: true });
    expect(applyButton()).toBeEnabled();
  });

  it("calls onApply when Apply is pressed", async () => {
    const user = userEvent.setup();
    const props = renderControls({ canApply: true });
    await user.click(applyButton());
    expect(props.onApply).toHaveBeenCalledTimes(1);
  });

  it("reports slider moves as draft changes without applying them", async () => {
    const user = userEvent.setup();
    const props = renderControls({ canApply: false });

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    expect(props.onLengthRangeChange).toHaveBeenCalledWith([21, 150]);
    expect(props.onApply).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run it and watch it fail**

Run: `npm test -- src/components/FilterControls.test.tsx`
Expected: FAIL — no button named "Apply filters" is rendered.

- [ ] **Step 4: Write the failing App test**

Create `frontend/src/App.filters.test.tsx`. It mocks `MapView` with a spy that records the props it was handed, which is exactly the draft-vs-applied boundary:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

const mapProps = vi.fn();

vi.mock("./lib/analytics", () => ({
  capture: vi.fn(),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: vi.fn().mockResolvedValue([]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: (props: Record<string, unknown>) => {
    mapProps(props);
    return <div data-testid="map" />;
  },
}));

function lastMapProps() {
  return mapProps.mock.calls.at(-1)?.[0] as {
    minLen: number;
    maxLen: number;
    minExposure: number;
    showAnchors: boolean;
  };
}

beforeEach(() => {
  mapProps.mockClear();
});

const applyButton = () => screen.getByRole("button", { name: /apply filters/i });

describe("App filter application", () => {
  it("keeps the map on the applied filters while the slider is moved", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(lastMapProps().minLen).toBe(20);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    expect(lastMapProps().minLen).toBe(20);
  });

  it("pushes the draft to the map only when Apply is pressed", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    await user.click(applyButton());

    expect(lastMapProps().minLen).toBe(21);
  });

  it("disables Apply until the draft diverges, and again once applied", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(applyButton()).toBeDisabled();

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    expect(applyButton()).toBeEnabled();

    await user.click(applyButton());
    expect(applyButton()).toBeDisabled();
  });

  it("sends the anchors toggle straight to the map without an Apply", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(lastMapProps().showAnchors).toBe(true);
    await user.click(screen.getByRole("checkbox", { name: /show anchors/i }));

    expect(lastMapProps().showAnchors).toBe(false);
    expect(applyButton()).toBeDisabled();
  });
});
```

- [ ] **Step 5: Run it and watch it fail**

Run: `npm test -- src/App.filters.test.tsx`
Expected: FAIL — no Apply button, and the map's `minLen` still tracks the slider.

- [ ] **Step 6: Rewrite FilterControls**

Replace the whole of `frontend/src/components/FilterControls.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { useI18n } from "@/lib/i18n";

export type LengthRange = [min: number, max: number];

interface FilterControlsProps {
  lengthRange: LengthRange;
  minExposure: number;
  showAnchors: boolean;
  canApply: boolean;
  onLengthRangeChange: (value: LengthRange) => void;
  onMinExposureChange: (value: number) => void;
  onShowAnchorsChange: (value: boolean) => void;
  onApply: () => void;
}

export function FilterControls(props: FilterControlsProps) {
  const { t } = useI18n();
  const [minLen, maxLen] = props.lengthRange;

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        props.onApply();
      }}
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("lineLength")}</Label>
          <span className="text-muted-foreground">
            {minLen}–{maxLen} m
          </span>
        </div>
        <Slider
          min={20}
          max={500}
          step={1}
          minStepsBetweenThumbs={1}
          value={props.lengthRange}
          onValueChange={([min, max]) => props.onLengthRangeChange([min, max])}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("minExposure")}</Label>
          <span className="text-muted-foreground">{props.minExposure} m</span>
        </div>
        <Slider
          min={0}
          max={300}
          step={1}
          value={[props.minExposure]}
          onValueChange={([value]) => props.onMinExposureChange(value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={props.showAnchors}
          onCheckedChange={(value) => props.onShowAnchorsChange(value === true)}
        />
        <span>{t("showAnchors")}</span>
      </label>
      <Button type="submit" className="w-full" disabled={!props.canApply}>
        {t("applyFilters")}
      </Button>
    </form>
  );
}
```

- [ ] **Step 7: Split App's filter state into draft and applied**

In `frontend/src/App.tsx`, add the defaults above the component (they are needed twice each, so name them):

```tsx
const DEFAULT_LENGTH_RANGE: LengthRange = [20, 150];
const DEFAULT_MIN_EXPOSURE = 30;
```

Replace the `lengthRange` / `minExposure` state declarations (currently `App.tsx:22-23`) with:

```tsx
  const [draftLengthRange, setDraftLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [draftMinExposure, setDraftMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
  const [appliedLengthRange, setAppliedLengthRange] = useState<LengthRange>(DEFAULT_LENGTH_RANGE);
  const [appliedMinExposure, setAppliedMinExposure] = useState(DEFAULT_MIN_EXPOSURE);
```

Delete `handleLengthRangeCommit` and `handleMinExposureCommit` (currently `App.tsx:45-55`, including the two-line comment above them about drag frames — it describes machinery that no longer exists) and put the apply handler in their place:

```tsx
  const canApply =
    draftLengthRange[0] !== appliedLengthRange[0] ||
    draftLengthRange[1] !== appliedLengthRange[1] ||
    draftMinExposure !== appliedMinExposure;

  const handleApply = useCallback(() => {
    setAppliedLengthRange(draftLengthRange);
    setAppliedMinExposure(draftMinExposure);
    capture("filters_applied", {
      min_len: draftLengthRange[0],
      max_len: draftLengthRange[1],
      min_exposure: draftMinExposure,
    });
  }, [draftLengthRange, draftMinExposure]);
```

Rewrite the `filters` node — the sliders bind to the draft, the button to `handleApply`:

```tsx
  const filters = (
    <FilterControls
      lengthRange={draftLengthRange}
      minExposure={draftMinExposure}
      showAnchors={showAnchors}
      canApply={canApply}
      onLengthRangeChange={setDraftLengthRange}
      onMinExposureChange={setDraftMinExposure}
      onShowAnchorsChange={setShowAnchors}
      onApply={handleApply}
    />
  );
```

Point the `summary` at the **applied** values — it describes what is on the map, not what is pending:

```tsx
  const summary = useMemo(
    () =>
      `${t("lineLength")} ${appliedLengthRange[0]}–${appliedLengthRange[1]} m - ${t("minExposure")} ${appliedMinExposure} m`,
    [t, appliedLengthRange, appliedMinExposure],
  );
```

And hand `MapView` the applied values (currently `App.tsx:128-130`):

```tsx
            minLen={appliedLengthRange[0]}
            maxLen={appliedLengthRange[1]}
            minExposure={appliedMinExposure}
```

- [ ] **Step 8: Run both new test files and watch them pass**

Run: `npm test -- src/components/FilterControls.test.tsx src/App.filters.test.tsx`
Expected: PASS, 8 tests.

- [ ] **Step 9: Update the analytics test for the new event**

`filter_changed` no longer exists. In `frontend/src/App.analytics.test.tsx`, replace the first two tests (`"emits filter_changed once when a slider commits"` and `"emits one filter_changed carrying both ends when the length max commits"`, currently lines 31-63) with these two. Leave the `restriction_layer_toggled` test and the whole mock block above it untouched:

```tsx
  it("emits nothing while a filter is only being drafted", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    const filterEvents = captureMock.mock.calls.filter(([event]) =>
      event.startsWith("filter"),
    );
    expect(filterEvents).toEqual([]);
  });

  it("emits filters_applied with the applied values when Apply is pressed", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");
    sliders[1].focus();
    await user.keyboard("{ArrowLeft}");
    await user.click(screen.getByRole("button", { name: /apply filters/i }));

    const applied = captureMock.mock.calls.filter(([event]) => event === "filters_applied");
    expect(applied).toHaveLength(1);
    expect(applied[0][1]).toEqual({ min_len: 21, max_len: 149, min_exposure: 30 });
  });
```

- [ ] **Step 10: Run the whole suite and the typechecker**

Run: `npm test`
Expected: PASS, every file green.

Run: `npx tsc -b`
Expected: no output (exit 0).

If `tsc` complains about an unused `onValueCommit` prop on the `Slider` wrapper, leave `src/components/ui/slider.tsx` alone — it is a passthrough wrapper and other callers may want it. Only remove it if `tsc` proves nothing else uses it.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.filters.test.tsx frontend/src/App.analytics.test.tsx \
        frontend/src/components/FilterControls.tsx frontend/src/components/FilterControls.test.tsx \
        frontend/src/lib/i18n/strings.ts
git commit -m "feat(web): apply filters with a button instead of searching per drag frame"
```

---

### Task 2: Close the mobile sheet on apply

On mobile the sheet covers the map, so applying without closing it hides the very result the user asked for. `App` takes ownership of the sheet's open state so `handleApply` can close it.

**Files:**
- Modify: `frontend/src/components/MobileControlSheet.tsx` (controlled `Sheet`; delete the dead `actions` prop)
- Modify: `frontend/src/App.tsx` (add `sheetOpen` state, close it in `handleApply`, pass `open`/`onOpenChange`)
- Create: `frontend/src/App.mobile.test.tsx`

**Interfaces:**
- Consumes: `handleApply` and `canApply` from Task 1; the `filters` node rendered into both layouts.
- Produces: `MobileControlSheetProps` gains `open: boolean` and `onOpenChange: (open: boolean) => void`, and loses `actions?: ReactNode`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/App.mobile.test.tsx`. The sheet's content only mounts while open, so `queryByRole("dialog")` going null is the assertion that it closed:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

vi.mock("./lib/analytics", () => ({
  capture: vi.fn(),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: vi.fn().mockResolvedValue([]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));

describe("mobile control sheet", () => {
  it("closes itself when the filters are applied", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /open controls/i }));

    const sheet = await screen.findByRole("dialog");
    const sliders = within(sheet).getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    await user.click(within(sheet).getByRole("button", { name: /apply filters/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: FAIL — the dialog is still in the document after Apply, because the sheet manages its own open state.

- [ ] **Step 3: Make the sheet controlled**

In `frontend/src/components/MobileControlSheet.tsx`, change the props interface — `actions` goes, `open`/`onOpenChange` arrive:

```tsx
interface MobileControlSheetProps {
  summary: string;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

Pass them to the root `Sheet`:

```tsx
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
```

And delete the now-dead actions line from the sheet body:

```tsx
          {props.actions ? props.actions : null}
```

- [ ] **Step 4: Let App own the sheet**

In `frontend/src/App.tsx`, add the state alongside the other `useState` calls:

```tsx
  const [sheetOpen, setSheetOpen] = useState(false);
```

Add the close to `handleApply` from Task 1 — the sheet must get out of the way of the result:

```tsx
  const handleApply = useCallback(() => {
    setAppliedLengthRange(draftLengthRange);
    setAppliedMinExposure(draftMinExposure);
    setSheetOpen(false);
    capture("filters_applied", {
      min_len: draftLengthRange[0],
      max_len: draftLengthRange[1],
      min_exposure: draftMinExposure,
    });
  }, [draftLengthRange, draftMinExposure]);
```

And wire the sheet up:

```tsx
          <MobileControlSheet
            summary={summary}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
            open={sheetOpen}
            onOpenChange={setSheetOpen}
          />
```

- [ ] **Step 5: Run the test and watch it pass**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the whole suite and the typechecker**

Run: `npm test`
Expected: PASS, every file green.

Run: `npx tsc -b`
Expected: no output (exit 0).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.mobile.test.tsx frontend/src/components/MobileControlSheet.tsx
git commit -m "feat(web): close the mobile filter sheet when filters are applied"
```

---

## Verification

After both tasks, drive the real app rather than trusting the tests alone:

- [ ] `npm run dev`, open the app, drag the length slider and confirm the network panel shows **no** `/zones` request until Apply is pressed.
- [ ] Confirm the button is greyed out on load, lights up as soon as a slider moves, and greys out again right after applying.
- [ ] Confirm "Show anchors" still toggles the anchor layer instantly, with no Apply needed.
- [ ] Narrow the viewport to mobile width, open the filter sheet, apply, and confirm the sheet closes onto the updated map.
