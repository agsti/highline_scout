# Tappable Mobile Filter Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label the collapsed mobile card as the filters card and make tapping it anywhere expand the sheet, replacing the dedicated `Filters` button with a chevron.

**Architecture:** Entirely inside `MobileControlSheet`. The card `<div>` gains an `onClick` that opens the sheet (pointer users tap anywhere); the chevron becomes the real `SheetTrigger` button (keyboard and screen-reader users keep a focusable, activatable control with `aria-expanded`). The `Filters` button is removed and its label becomes a muted caption row.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind, shadcn/Radix UI, lucide-react icons, Vitest + Testing Library.

## Global Constraints

- Work from `/home/gus/projects/highliner_finder`. Frontend commands run from `frontend/`.
- **Bare `npm` does not work in this shell** — the user's zsh has a broken nvm lazy-load hook and `npm` dies in a `command_not_found_handler`. The only invocation that works:

  ```bash
  cd frontend
  PATH="/home/gus/.nvm/versions/node/v20.20.2/bin:$PATH" /home/gus/.nvm/versions/node/v20.20.2/bin/npm <cmd>
  ```

  Use that form wherever this plan says `npm test` or `npm run build`.
- Baseline before this task: **78 tests passing across 18 files**. Leave the suite green.
- **The card div's handler must be `props.onOpenChange(true)` — never a toggle.** Clicking the chevron fires both the `SheetTrigger` and the card's `onClick` (the click bubbles up), so both paths must converge on "open" for the double-fire to be idempotent. A toggle would cancel the trigger out and the chevron would appear dead.
- No new i18n strings. The caption reuses the existing `filters` key; the chevron keeps the existing `openControls` label, which is why the three existing tests that query `/open controls/i` keep working.
- `RestrictionLegend` must NOT change — it stays outside any button, so its `<ul>`/`<li>` markup stays valid. It already owns its own `mt-2` top margin, so the card needs no wrapper around `{props.legend}`.
- `App.tsx`, `DesktopSidebar`, and the sheet's contents are out of scope. Keep `data-testid="mobile-summary-card"` on the card's root div — three tests depend on it.
- Tests run under jsdom, where `I18nProvider` resolves to **English**. Assert against English strings.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/components/MobileControlSheet.tsx` | Modify: card becomes tappable; caption row + chevron replace the `Filters` button. |
| `frontend/src/App.mobile.test.tsx` | Modify: add the tap-the-body test. |

---

## Task 1: Make the whole card tap to expand

**Files:**
- Modify: `frontend/src/components/MobileControlSheet.tsx:1-38`
- Test: `frontend/src/App.mobile.test.tsx`

**Interfaces:**
- Consumes: `MobileControlSheetProps` as it stands today (`summary`, `legend`, `filters`, `restrictions`, `statuses`, `caveat`, `open`, `onOpenChange`). **No prop changes** — `App.tsx` is untouched.
- Produces: nothing new for later tasks. This is the only task.

- [ ] **Step 1: Write the failing test**

Add this test to the existing `describe("mobile control sheet", ...)` block in `frontend/src/App.mobile.test.tsx`. Leave the mocks and the three existing tests alone.

```tsx
  it("expands the sheet when the card body is tapped", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /i understand/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const card = screen.getByTestId("mobile-summary-card");

    // The summary text is not a button — tapping it must still open the sheet.
    await user.click(within(card).getByText("20–150 m · exp ≥30 m"));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: FAIL — `Unable to find role="dialog"`. The summary text has no click handler today, so tapping it does nothing.

- [ ] **Step 3: Rewrite the collapsed card**

In `frontend/src/components/MobileControlSheet.tsx`, add `ChevronUp` to the lucide import:

```tsx
import { ChevronUp, SlidersHorizontal } from "lucide-react";
```

Then replace the card `<div>` (currently lines 23-38) with:

```tsx
      <div
        data-testid="mobile-summary-card"
        onClick={() => props.onOpenChange(true)}
        className="fixed inset-x-3 bottom-3 z-[1100] cursor-pointer rounded-xl border bg-card/95 p-3 shadow-xl backdrop-blur"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-border" />
        <div className="flex items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" />
            {t("filters")}
          </div>
          <SheetTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0"
              aria-label={t("openControls")}
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
          </SheetTrigger>
        </div>
        <div className="mt-1 text-sm font-medium">{props.summary}</div>
        {props.legend}
      </div>
```

Three things to note, so you don't "fix" them:
- The card's `onClick` calls `props.onOpenChange(true)`, not a toggle. See Global Constraints — a toggle breaks the chevron.
- `{props.legend}` stays a bare child. `RestrictionLegend` returns `null` when no layer is enabled and owns its own `mt-2`, so no conditional wrapper is needed.
- The chevron keeps `aria-label={t("openControls")}`. Do not remove it — three existing tests find the trigger by that name.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- src/App.mobile.test.tsx`
Expected: PASS — 4 tests (the 3 existing plus the new one).

- [ ] **Step 5: Run the full suite**

Run: `npm test`
Expected: PASS — 18 files, 79 tests (the new test lands in an existing file, so the file count does not change).

- [ ] **Step 6: Typecheck**

Run: `npm run build`
Expected: exit 0, no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/MobileControlSheet.tsx frontend/src/App.mobile.test.tsx
git commit -m "feat(web): expand the mobile sheet by tapping anywhere on the filter card"
```

---

## Verification

After Task 1, drive the real app rather than trusting the suite. Run `npm run dev`, open it at a mobile viewport (~390px wide), and confirm:

- The card reads `⚙ FILTERS` on its caption row with a chevron at the right, and the summary below it. No `Filters` button.
- Tapping the summary text, the legend, the caption, or the card's empty padding all open the sheet.
- Tapping the chevron opens the sheet exactly once — it must NOT open-then-close (that would mean the card's handler is toggling instead of setting `true`).
- Tabbing to the chevron and pressing Enter opens the sheet.
