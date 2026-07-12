# Desktop Restriction Definitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep desktop restriction controls permanently visible and move their definitions into a compact adjacent card opened from per-row help buttons.

**Architecture:** `RestrictionLayerControls` remains the owner of restriction-row rendering and gains the desktop-only definition interaction, while responsive classes preserve the existing mobile inline definitions. `FiltersPanel` becomes a single-disclosure card whose restrictions section is static; its outer positioning container permits the adjacent definition card to overflow while an inner shell retains the existing rounded clipping. The obsolete swatch-summary data path is removed from `App` and `MapChrome`.

**Tech Stack:** React 18, TypeScript 5.7, Tailwind CSS, lucide-react, Vitest, Testing Library

## Global Constraints

- The mobile control sheet and map restriction behavior remain unchanged.
- Existing restriction selection, analytics, localization sources, and map legend behavior remain unchanged.
- The desktop restrictions section is always visible while the filters pane is expanded.
- Keep the Restrictions heading, but remove its summary color swatches and disclosure chevron.
- Do not render a selected restriction's definition inline on desktop.
- At most one adjacent definition card is open; the active help button, an outside click, or collapsing the filters pane closes it.
- The definition card is immediately right of the filter card and aligned with the top of the restrictions section.

---

### Task 1: Build the permanent desktop restrictions section and definition card

**Files:**
- Modify: `frontend/src/components/RestrictionLayerControls.tsx`
- Modify: `frontend/src/components/RestrictionLayerControls.test.tsx`
- Modify: `frontend/src/components/FiltersPanel.tsx`
- Modify: `frontend/src/components/FiltersPanel.test.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/i18n/strings.ts`
- Test: `frontend/src/lib/i18n/i18n.test.tsx`

**Interfaces:**
- `RestrictionLayerControls` keeps its existing public props: `{ layers, enabled, onEnabledChange }`.
- Add the catalog key `restrictionInfo: "About {name}"` in English, with equivalent Catalan and Spanish translations, for each help button's accessible name.
- Remove `swatches: string[]` from `FiltersPanelProps` and `MapChromeProps`; no replacement prop is needed.

- [ ] **Step 1: Replace the disclosure-oriented panel test with failing permanent-section tests**

Update `frontend/src/components/FiltersPanel.test.tsx` so `renderPanel()` no longer passes `swatches`, and replace the nested-disclosure test with:

```tsx
it("keeps restrictions visible whenever the filters pane is expanded", async () => {
  const user = userEvent.setup();
  renderPanel();

  expect(screen.getByText("panel restrictions")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restrictions" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Minimize panel" }));
  expect(screen.getByRole("button", { name: "Expand panel" })).toHaveAttribute("aria-expanded", "false");
});
```

Keep the existing whole-panel collapse test. This test intentionally checks DOM structure and accessible controls; CSS visibility itself is represented by the existing grid-row collapse state.

- [ ] **Step 2: Add failing definition interaction tests**

Expand `frontend/src/components/RestrictionLayerControls.test.tsx` with two layers whose translated tooltip/highlight values come from the existing test fixtures, and add tests equivalent to:

```tsx
it("opens one desktop definition at a time and toggles the active definition", async () => {
  const user = userEvent.setup();
  renderControls();

  const zepaInfo = screen.getByRole("button", { name: /About.*ZEPA/i });
  await user.click(zepaInfo);
  expect(zepaInfo).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("dialog")).toHaveTextContent(layers[0].tooltip);

  const zecInfo = screen.getByRole("button", { name: /About.*ZEC/i });
  await user.click(zecInfo);
  expect(zepaInfo).toHaveAttribute("aria-expanded", "false");
  expect(zecInfo).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("dialog")).toHaveTextContent(layers[1].tooltip);

  await user.click(zecInfo);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("closes the definition when clicking outside", async () => {
  const user = userEvent.setup();
  renderControls();
  await user.click(screen.getByRole("button", { name: /About.*ZEPA/i }));
  await user.click(document.body);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
```

Also assert that a checked restriction's definition has no ordinary desktop inline paragraph. Use a stable semantic marker or test id only if necessary to distinguish the responsive mobile copy from the dialog copy; do not assert Tailwind implementation details alone.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd frontend && npm test -- --run src/components/FiltersPanel.test.tsx src/components/RestrictionLayerControls.test.tsx
```

Expected: FAIL because the nested Restrictions disclosure still exists, help buttons/dialog do not exist, and `swatches` is still required.

- [ ] **Step 4: Implement the compact rows and adjacent definition card**

In `RestrictionLayerControls.tsx`:

- Import `CircleHelp` from `lucide-react` and React's `useEffect`, `useId`, `useRef`, and `useState`.
- Keep `HighlightedText`, but use it inside both the mobile-only inline definition and the desktop definition card.
- Track `activeDefinitionId: string | null`.
- Put the controls and adjacent card in a `relative` root with a ref. While a definition is active, register a `pointerdown` listener on `document`; close only when the event target is outside the root, and remove the listener in cleanup.
- Render each row compactly. Keep checkbox, color marker, and label. Add a desktop-only help button with `aria-label={t("restrictionInfo", { name: tx.label })}`, `aria-expanded`, and `aria-controls` pointing to a stable `useId()`-derived card id when active.
- Preserve the existing checked-only definition below the row with `md:hidden`, so mobile behavior does not change. Mark this paragraph with `data-testid="mobile-restriction-definition"` if the tests need a semantic distinction in jsdom.
- Render the active definition card with `role="dialog"`, `aria-labelledby`, and desktop-only classes. Position it using `absolute left-[calc(100%+1rem)] top-0 w-[296px]`; give it the same card background, rounded corners, border/shadow, and readable padding as the filters card. Its heading is the active translated label and its body uses `HighlightedText` with the translated tooltip/highlight.

The essential state transition is:

```tsx
onClick={() => setActiveDefinitionId((current) => (current === layer.id ? null : layer.id))}
```

Do not duplicate restriction translation logic: derive the active layer and call `restrictionText(activeLayer.id, lang, activeLayer)` exactly as rows already do.

- [ ] **Step 5: Make the restrictions section static and allow the card to overflow**

In `FiltersPanel.tsx`:

- Remove `ChevronRight`, `restrictionsExpanded`, `swatches`, and the nested button/grid animation.
- Keep the outer absolute positioning container but remove `overflow-hidden` from it.
- Add an inner wrapper carrying `overflow-hidden rounded-[14px] bg-card/[0.97] shadow-panel backdrop-blur-[10px]` so the main card retains its appearance.
- Under filters/statuses, render a static restrictions section with a top border, non-button heading, and the `restrictions` node beneath it.
- Ensure clicking the whole-panel minimize button counts as an outside pointer interaction for `RestrictionLayerControls`, closing any open definition before the panel finishes collapsing.

The static section should have this shape:

```tsx
<div className="border-t border-hairline-soft">
  <div className="px-3.5 pt-[11px] text-[13px] font-bold text-primary-deep">
    {t("restrictions")}
  </div>
  <div className="px-3.5 pb-3.5 pt-3">{restrictions}</div>
</div>
```

- [ ] **Step 6: Remove the obsolete swatch data path and add translated accessible copy**

In `MapChrome.tsx`, remove `swatches` from `MapChromeProps` and from the `FiltersPanel` call. In `App.tsx`, delete the `swatches` memo and stop passing it to `MapChrome`; preserve the other memos and all restriction/map props.

Add this key to all three catalogs in `frontend/src/lib/i18n/strings.ts`:

```ts
// ca
restrictionInfo: "Sobre {name}",
// es
restrictionInfo: "Sobre {name}",
// en
restrictionInfo: "About {name}",
```

The existing catalog-parity test must remain unchanged and pass.

- [ ] **Step 7: Run focused tests and type/build verification**

Run:

```bash
cd frontend && npm test -- --run src/components/FiltersPanel.test.tsx src/components/RestrictionLayerControls.test.tsx src/lib/i18n/i18n.test.tsx
```

Expected: all focused tests PASS with pristine output.

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite production build PASS.

- [ ] **Step 8: Run the full frontend suite**

Run:

```bash
cd frontend && npm test
```

Expected: all frontend tests PASS with pristine output.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/RestrictionLayerControls.tsx frontend/src/components/RestrictionLayerControls.test.tsx frontend/src/components/FiltersPanel.tsx frontend/src/components/FiltersPanel.test.tsx frontend/src/components/MapChrome.tsx frontend/src/App.tsx frontend/src/lib/i18n/strings.ts
git commit -m "feat(web): show desktop restriction definitions"
```
