# Favicon Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the supplied SVG, 32px PNG, and 180px PNG favicon assets and declare them in the frontend document head.

**Architecture:** Vite exposes files in `frontend/public/` at the application root in both local development and the production build. The static `frontend/index.html` head will use root-relative links to those copied assets; no React runtime code changes are needed.

**Tech Stack:** Vite, React, TypeScript, Vitest, HTML.

## Global Constraints

- Extract only `favicon.svg`, `favicon-32.png`, and `favicon-180.png` from `Webapp icon design request.zip`.
- Keep the supplied root-relative paths and link attributes exactly as specified.
- Do not add other logo exports or change application behavior.

---

### Task 1: Publish favicon assets and document links

**Files:**
- Create: `frontend/public/favicon.svg`
- Create: `frontend/public/favicon-32.png`
- Create: `frontend/public/favicon-180.png`
- Modify: `frontend/index.html:5-31`
- Test: build artifact inspection of `frontend/dist/index.html` and its three favicon files

**Interfaces:**
- Consumes: the three named files in `Webapp icon design request.zip` under `export/`
- Produces: `/favicon.svg`, `/favicon-32.png`, and `/favicon-180.png` static URLs referenced by the browser head

- [x] **Step 1: Write the failing verification script**

Run the production build, then assert the artifact has the expected icon declarations and files:

```bash
cd frontend
npm run build
grep -F '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' dist/index.html
grep -F '<link rel="icon" href="/favicon-32.png" sizes="32x32" />' dist/index.html
grep -F '<link rel="apple-touch-icon" href="/favicon-180.png" />' dist/index.html
test -f dist/favicon.svg
test -f dist/favicon-32.png
test -f dist/favicon-180.png
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run build && grep -F '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' dist/index.html`

Expected: the build succeeds, but `grep` exits 1 because the SVG declaration has not been added.

- [x] **Step 3: Add the supplied assets and minimal HTML declarations**

Extract the three archive members to `frontend/public/` while stripping the `export/` directory. Insert the following immediately after the viewport metadata in `frontend/index.html`:

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="icon" href="/favicon-32.png" sizes="32x32" />
<link rel="apple-touch-icon" href="/favicon-180.png" />
```

- [x] **Step 4: Run the production verification**

Run the full Step 1 command.

Expected: the Vite production build succeeds, every `grep` returns its exact link, and all three files exist in `frontend/dist/`.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/public/favicon.svg frontend/public/favicon-32.png frontend/public/favicon-180.png docs/superpowers/plans/2026-07-14-favicon-implementation.md
git commit -m "feat: add site favicons"
```
