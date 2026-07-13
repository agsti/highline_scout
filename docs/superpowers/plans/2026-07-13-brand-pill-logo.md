# BrandPill Logo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the standalone Highline Scout SVG as the accessible BrandPill content.

**Architecture:** `BrandPill` continues to provide the existing visual pill container and renders its logo through a native image element. The image's alternative text supplies the component's accessible name, replacing the former heading.

**Tech Stack:** React, TypeScript, Tailwind CSS, Vitest, Testing Library.

## Global Constraints

Use `frontend/assets/logo.svg`; render `Highline Scout` only as the image alternative text; keep the existing pill container styling.

---

### Task 1: BrandPill logo rendering

**Files:**
- Modify: `frontend/src/components/FloatingNav.test.tsx`
- Modify: `frontend/src/components/BrandPill.tsx`

**Interfaces:**
- Consumes: `frontend/assets/logo.svg`
- Produces: an image exposed to assistive technology as `Highline Scout`

- [ ] **Step 1: Write the failing test**

```tsx
expect(screen.getByRole("img", { name: "Highline Scout" })).toHaveAttribute(
  "src",
  "/assets/logo.svg",
);
expect(screen.queryByRole("heading", { name: "Highline Scout" })).not.toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/components/FloatingNav.test.tsx`
Expected: FAIL because BrandPill has no accessible image.

- [ ] **Step 3: Write minimal implementation**

```tsx
<img alt="Highline Scout" className="..." src="/assets/logo.svg" />
```

Remove the old `HS` span and visible heading while retaining the surrounding pill element and its classes.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/components/FloatingNav.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/BrandPill.tsx frontend/src/components/FloatingNav.test.tsx docs/superpowers/plans/2026-07-13-brand-pill-logo.md
git commit -m "feat(web): use logo in brand pill"
```
