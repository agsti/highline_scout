# Task 3 Report: LanguageSwitcher segmented variant

## Status: DONE

## Files changed

### `frontend/src/components/LanguageSwitcher.tsx`
- Added `LanguageSwitcherProps` with `variant?: "pill" | "segmented"`, defaulting to `"pill"`.
- `SHORT` and `NAMES` maps are byte-for-byte unchanged. `LANGS`/`setLang` usage unchanged — a single `LANGS.map` loop renders both variants; no duplication.
- Group `div`: segmented variant adds `rounded-[8px] bg-accent p-0.5` (container radius per handoff, not `rounded-lg`); pill keeps `pr-1`.
- Segment `button`: segmented uses `rounded-[6px] px-2 py-1 text-[11px]` (segment radius per handoff, not `rounded-md`); pill keeps the original `rounded-full px-[9px] py-[7px] text-[11px] md:px-[11px] md:py-2 md:text-xs`.
- Active-state styling branches by variant: segmented active gets `bg-card font-bold text-primary-deep shadow-[0_1px_3px_rgba(22,48,42,0.12)]` (the one permitted raw-value shadow, per the handoff's fixed alpha); pill active keeps `bg-primary font-bold text-primary-foreground`.
- Inactive hover branches too: segmented uses `hover:bg-card/60` (since `hover:bg-accent` would be invisible against the segmented track's own `bg-accent`); pill keeps `hover:bg-accent`.
- All classes use existing design tokens (`primary-deep`, `card`, `accent`, `muted-foreground`, `primary`, `primary-foreground`); the only raw value is the mandated shadow.

### `frontend/src/components/LanguageSwitcher.test.tsx`
- Appended a new `describe("LanguageSwitcher segmented variant", ...)` block (verbatim from the brief) with two tests:
  1. `wraps the segments in an accent track and lifts the active one` — asserts the group has `bg-accent` and the active segment (`Català`) has `bg-card` while the inactive one (`Español`) does not.
  2. `still switches language in the segmented variant` — clicks `English` and asserts `aria-pressed="true"`.
- The two pre-existing `describe("LanguageSwitcher", ...)` pill-variant tests were left completely unchanged.

## Consumers verified untouched
- `frontend/src/components/FloatingNav.tsx:19` — `<LanguageSwitcher />` (no props) — not edited.
- `frontend/src/components/SafetyDisclaimerDialog.tsx:34` — `<LanguageSwitcher />` (no props) — not edited.
Both fall through to the `variant = "pill"` default, so their rendered output is unchanged.

## Test commands and real output

Note: the shell has a broken nvm zsh hook (known issue, see MEMORY.md `node-shell-broken`). Worked around per-invocation with:
`unset -f npm node npx _load_nvm; export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"`

### Step 2 — run tests before implementing (expected FAIL)
Command: `cd frontend && npm test -- LanguageSwitcher`

```
 ❯ src/components/LanguageSwitcher.test.tsx (4 tests | 1 failed) 87ms
   × LanguageSwitcher segmented variant > wraps the segments in an accent track and lifts the active one 5ms
     → expect(element).toHaveClass("bg-accent")

Expected the element to have class:
  bg-accent
Received:
  flex items-center gap-0.5 pr-1

 Test Files  1 failed (1)
      Tests  1 failed | 3 passed (4)
```

This confirms the failure predicted by the brief (the group had no `bg-accent` since the variant didn't exist yet; Vitest's esbuild transform doesn't do a separate type-check pass, so the TS prop-rejection surfaced as this runtime assertion failure instead of a compile error — `tsc --noEmit` below is what actually enforces the type).

### Step 4 — run tests after implementing (expected PASS)
Command: `cd frontend && npm test -- LanguageSwitcher`

```
 ✓ src/components/LanguageSwitcher.test.tsx (4 tests) 104ms

 Test Files  1 passed (1)
      Tests  4 passed (4)
```

All 4 tests pass: the 2 new segmented-variant tests plus the 2 pre-existing pill-variant tests (regression guard), confirmed passing unchanged.

### Type check
Command: `cd frontend && npx tsc --noEmit`
Output: (empty — no errors)

## Commit
```
f5f7604da6c77bee61e0c6ef1573af9e6986cc7c feat(web): add segmented variant to LanguageSwitcher
 2 files changed, 55 insertions(+), 6 deletions(-)
```
Only `src/components/LanguageSwitcher.tsx` and `src/components/LanguageSwitcher.test.tsx` were staged and committed (an unrelated pre-existing modification to `.superpowers/sdd/task-2-report.md` was left out of this commit).

## Concerns
- `.superpowers/sdd/task-3-report.md` previously held a report for an unrelated "anchor and restriction overlay extraction" task (from a different plan, `docs/superpowers/plans/2026-07-12-map-view-decomposition.md`). That content has been overwritten with this task's report — flag in case that other report needs to be preserved elsewhere.
- Otherwise none functional: diff matches the brief's prescribed code exactly; both existing consumers verified unedited and unaffected.
