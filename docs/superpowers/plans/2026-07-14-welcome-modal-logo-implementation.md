# Welcome Modal Logo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brand the first-run safety disclaimer with the existing logo while removing its duplicated product-name title.

**Architecture:** `SafetyDisclaimerDialog` will import the bundled SVG and render it in its existing top row, immediately before the language selector. The title element is removed; dialog behavior, translated safety content, and acknowledgement flow remain intact.

**Tech Stack:** React, TypeScript, Vite asset imports, Vitest, Testing Library.

## Global Constraints

- Use `frontend/src/assets/logo.svg`; do not add a duplicate asset.
- Render an accessible image with `alt="HighlineScout"`.
- Keep the language switcher aligned at the right edge of the header row.
- Do not change disclaimer copy, modal blocking behavior, or acceptance behavior.

---

### Task 1: Brand the safety disclaimer header

**Files:**
- Modify: `frontend/src/components/SafetyDisclaimerDialog.test.tsx`
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx`

**Interfaces:**
- Consumes: `logo.svg` as a Vite-imported `string` URL and the existing `SafetyDisclaimerDialogProps` interface.
- Produces: `SafetyDisclaimerDialog` renders an accessible HighlineScout logo in its header without an `h2` title.

- [ ] **Step 1: Write the failing test**

In the existing `explains that HighlineScout only suggests spots and lists scouting safeguards` test, add assertions for the image and removal of the heading:

```tsx
expect(screen.getByRole("img", { name: "HighlineScout" })).toBeInTheDocument();
expect(screen.queryByRole("heading", { name: "HighlineScout" })).not.toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- SafetyDisclaimerDialog.test.tsx
```

Expected: FAIL because no image named `HighlineScout` is rendered and the existing title heading is still present.

- [ ] **Step 3: Write minimal implementation**

In `SafetyDisclaimerDialog.tsx`, replace the `DialogHeader` / `DialogTitle` usage with a single header row and import the existing asset:

```tsx
import logo from "@/assets/logo.svg";
```

```tsx
<div className="flex items-center justify-between gap-4">
  <img src={logo} alt="HighlineScout" className="h-8 w-auto" />
  <LanguageSwitcher />
</div>
```

Remove the now-unused `DialogHeader` and `DialogTitle` imports. Leave the translated disclaimer body and `Button` untouched.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npm test -- SafetyDisclaimerDialog.test.tsx
```

Expected: PASS, including the existing modal-interaction tests.

- [ ] **Step 5: Run frontend regression suite**

Run:

```bash
just test-web
```

Expected: PASS with all frontend tests green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SafetyDisclaimerDialog.tsx frontend/src/components/SafetyDisclaimerDialog.test.tsx
git commit -m "feat: brand welcome modal"
```
