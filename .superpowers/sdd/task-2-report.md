# Task 2: Popover Primitive — Implementation Report

## Status: DONE

**Commit SHA:** 846e729

## Changes Per File

### 1. `frontend/src/components/ui/popover.tsx` (CREATED)
- Implemented the Popover component following the exact requirements from task-2-brief.md
- Uses Radix UI's `@radix-ui/react-popover` primitive
- Exports three components: `Popover` (Root), `PopoverTrigger`, `PopoverContent`
- `PopoverContent` uses `React.forwardRef` with proper TypeScript types
- Applied default props: `align="end"`, `sideOffset={8}`
- Styled with Tailwind classes:
  - `z-[1110]` for z-index positioning
  - `rounded-2xl` (16px radius) as specified in handoff
  - `shadow-menu` from design tokens
  - Animation classes for state transitions
  - `origin-[var(--radix-popover-content-transform-origin)]` for proper scale origin
- Wrapped content in `PopoverPrimitive.Portal` for dom positioning
- Matched house style of `dialog.tsx`: forwardRef pattern, cn() usage, displayName convention

### 2. `frontend/src/components/ui/popover.test.tsx` (CREATED)
- Two test cases covering core functionality:
  1. "renders the portaled panel above the map panes when opened" — verifies:
     - Panel is not in document initially
     - Clicking trigger opens the panel
     - Panel has correct z-[1110] class
  2. "closes on Escape" — verifies:
     - Panel opens on trigger click
     - Panel is removed from document after Escape key press

### 3. `frontend/package.json` (MODIFIED)
- Added dependency: `@radix-ui/react-popover@^1.1.6`
- Transitive dependencies (dismissable-layer, focus-scope, portal, popper, presence) were already present via dialog/select

### 4. `frontend/package-lock.json` (MODIFIED)
- Updated with new package entries and lockfile entries for @radix-ui/react-popover

## Test Execution

### Step 1: Install Dependency
```bash
bash -c 'cd /home/gus/projects/highliner_finder/frontend && /home/gus/.nvm/versions/node/v20.20.2/bin/node /home/gus/.nvm/versions/node/v20.20.2/bin/npm install @radix-ui/react-popover@^1.1.6'
```

**Output:**
```
added 2 packages, and audited 315 packages in 1s
51 packages are looking for funding
  run `npm fund` for details
5 vulnerabilities (3 moderate, 1 high, 1 critical)
```

### Step 2: Initial Test Run (EXPECTED FAIL)
**Command:** `npm test -- popover` (before creating popover.tsx)

**Output:**
```
FAIL  src/components/ui/popover.test.tsx [ src/components/ui/popover.test.tsx ]
Error: Failed to resolve import "./popover" from "src/components/ui/popover.test.tsx". Does the file exist?
  Plugin: vite:import-analysis
  File: /home/gus/projects/highliner_finder/frontend/src/components/ui/popover.test.tsx:4:56
```

This is the expected failure — module not found error.

### Step 3: Implementation Created
Created `popover.tsx` with the exact code from the brief.

### Step 4: Final Test Run (PASS)
```bash
bash -c 'cd /home/gus/projects/highliner_finder/frontend && /home/gus/.nvm/versions/node/v20.20.2/bin/node ./node_modules/vitest/vitest.mjs run popover'
```

**Output:**
```
 RUN  v2.1.9 /home/gus/projects/highliner_finder/frontend

 ✓ src/components/ui/popover.test.tsx (2 tests) 107ms

 Test Files  1 passed (1)
      Tests  2 passed (2)
   Start at  20:56:39
   Duration  743ms (transform 46ms, setup 41ms, collect 132ms, tests 107ms, environment 179ms, prepare 133ms)
```

Both test cases passed successfully.

### Step 5: TypeScript Check
```bash
bash -c 'cd /home/gus/projects/highliner_finder/frontend && /home/gus/.nvm/versions/node/v20.20.2/bin/node ./node_modules/typescript/bin/tsc --noEmit'
```

**Output:** (no errors - clean TypeScript check)

### Step 6: Commit
```bash
git add frontend/src/components/ui/popover.tsx frontend/src/components/ui/popover.test.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(web): add popover primitive"
```

**Result:**
```
[feat/nav-menu-system 846e729] feat(web): add popover primitive
 4 files changed, 107 insertions(+)
 create mode 100644 frontend/src/components/ui/popover.test.tsx
 create mode 100644 frontend/src/components/ui/popover.tsx
```

## Notes & Concerns

### Environment Issues Encountered & Resolved
- The zsh nvm hook was broken (as noted in MEMORY.md), causing "command not found: _load_nvm" errors
- Workaround: Used bash shell with explicit full path to node binary: `/home/gus/.nvm/versions/node/v20.20.2/bin/node`
- This did not affect implementation quality, only the command execution method

### Design Decisions & Confirmations
1. **Radix Popover (not DropdownMenu)**: Correctly used `@radix-ui/react-popover` as specified. DropdownMenu was explicitly forbidden due to its menu-item semantics conflicting with the language segmented control that will be placed in the panel footer.

2. **Z-index value**: Confirmed `z-[1110]` matches design handoff and test expectation. Tests verify this class is present on the rendered content.

3. **Styling choices**: 
   - `rounded-2xl` = 16px radius (per handoff)
   - `shadow-menu` token exists (per Task 1 context)
   - Animation classes follow Radix data attributes pattern: `data-[state=open]:animate-in`, etc.

4. **Transform origin**: Used `origin-[var(--radix-popover-content-transform-origin)]` to enable proper scale animations from the correct corner (Radix provides this CSS custom property).

5. **Portal wrapping**: Content is wrapped in `PopoverPrimitive.Portal` to ensure it renders above z-index stacking contexts.

### Code Quality
- Followed house style exactly from `dialog.tsx`
- Used forwardRef pattern with proper TypeScript ElementRef typing
- Applied cn() utility for className merging with defaults
- Set displayName for dev tools debugging
- Double quotes, semicolons, 2-space indent throughout (matching project style)

## Summary

Task 2 completed successfully. The popover primitive is now available as a reusable shadcn-style component following Radix UI best practices. Both test cases pass (open/close via trigger, dismiss via Escape). TypeScript check clean. Ready for Task 3 (building the menu on top of this primitive).

---

# Task 2 Fix Report: Review Findings Remediation

## Status: DONE

## Findings Addressed

### Finding 1 (Important): `PopoverContent`'s default props were untested
Added a new test to `frontend/src/components/ui/popover.test.tsx` that renders
`<PopoverContent>` with no explicit `align`/`sideOffset` props and asserts the
`align="end"` default took effect.

**Investigation:** jsdom does not run Popper's real layout math, so pixel-position
assertions are impossible. Probed what Radix actually emits in jsdom by rendering
the component and dumping `outerHTML`:

```
<div data-side="bottom" data-align="end" data-state="open" role="dialog" ...>panel</div>
```

Confirmed `data-align="end"` IS emitted by Radix in jsdom (independent of layout —
it reflects the resolved `align` prop, not computed position), so the test asserts
on that real attribute:

```tsx
it("defaults to end alignment when align/sideOffset are not specified", async () => {
  const user = userEvent.setup();

  render(
    <Popover>
      <PopoverTrigger aria-label="Open">trigger</PopoverTrigger>
      <PopoverContent>panel</PopoverContent>
    </Popover>,
  );

  await user.click(screen.getByRole("button", { name: "Open" }));

  expect(screen.getByText("panel")).toHaveAttribute("data-align", "end");
});
```

`sideOffset` has no observable DOM reflection in jsdom (it only feeds floating-ui's
offset math, which jsdom doesn't compute), so no assertion was fabricated for it —
per the brief's explicit instruction not to assert on something vacuous.

### Finding 2 (Minor): test name overclaimed
Renamed the first test from "renders the portaled panel above the map panes when
opened" (asserts only `z-[1110]`, proves nothing about stacking — no map pane is
rendered) to "opens the panel and tags it with the map-pane z-index", which
accurately describes the assertion. The assertion itself (`toHaveClass("z-[1110]")`)
was left unchanged.

## Covering Test File
`frontend/src/components/ui/popover.test.tsx`

## Verification

### Command
```bash
cd frontend && npm test -- popover
```

### Output — after fix, all 3 tests pass
```
 RUN  v2.1.9 /home/gus/projects/highliner_finder/frontend

 ✓ src/components/ui/popover.test.tsx (3 tests) 122ms

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  21:04:31
   Duration  797ms (transform 47ms, setup 42ms, collect 140ms, tests 122ms, environment 199ms, prepare 173ms)
```

### Deliberate-break check (proves the new test is not vacuous)

Temporarily changed `frontend/src/components/ui/popover.tsx` line 11 from:
```tsx
>(({ className, align = "end", sideOffset = 8, ...props }, ref) => (
```
to:
```tsx
>(({ className, align, sideOffset = 8, ...props }, ref) => (
```

Re-ran `npm test -- popover`:
```
 RUN  v2.1.9 /home/gus/projects/highliner_finder/frontend

 ❯ src/components/ui/popover.test.tsx (3 tests | 1 failed) 131ms
   × Popover > defaults to end alignment when align/sideOffset are not specified 26ms
     → expect(element).toHaveAttribute("data-align", "end") // element.getAttribute("data-align") === "end"

Expected the element to have attribute:
  data-align="end"
Received:
  data-align="center"

⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/components/ui/popover.test.tsx > Popover > defaults to end alignment when align/sideOffset are not specified
Error: expect(element).toHaveAttribute("data-align", "end") // element.getAttribute("data-align") === "end"

Expected the element to have attribute:
  data-align="end"
Received:
  data-align="center"

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed (3)
```

New test FAILED as expected (Radix falls back to its own default `align="center"`
when the prop is undefined). Restored the `align = "end"` default in
`popover.tsx` (verified `git diff -- frontend/src/components/ui/popover.tsx` is
empty, confirming no residual behavior change), then re-ran:

```
 RUN  v2.1.9 /home/gus/projects/highliner_finder/frontend

 ✓ src/components/ui/popover.test.tsx (3 tests) 120ms

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  21:04:47
   Duration  766ms
```

All 3 tests pass again. `popover.tsx` is unchanged from before the fix
(behavior-neutral — only `popover.test.tsx` was modified for this fix).

## Commit
See git log for the commit SHA covering this fix.
