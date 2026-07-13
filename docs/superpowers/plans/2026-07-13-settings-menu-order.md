# Settings Menu Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show settings in the order Areas, Language, Feedback, and About, while removing the menu-only Safety dialog path.

**Architecture:** `NavMenu` owns the menu layout and will render its control sections before the two retained actions. `FloatingNav`, `MapChrome`, and `App` will stop forwarding and storing the removed Safety action. The first-visit `SafetyDisclaimerDialog` remains part of `App` and its safety copy remains in i18n.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, Vite.

## Global Constraints

- Keep `SafetyDisclaimerDialog` and its initial acknowledgement behavior unchanged.
- Remove `SafetyDialog` and all production/test references used only by the menu action.
- Keep Feedback behavior unchanged: it displays the existing in-menu coming-soon hint without closing the menu.
- Preserve all three restriction-area mode choices and the segmented language selector.
- Use the repository frontend commands from `frontend/package.json`; Node must be version 20 or newer.

---

## File Structure

- Modify: `frontend/src/components/NavMenu.tsx` — reorder menu sections and remove the Safety action API and icon.
- Modify: `frontend/src/components/NavMenu.test.tsx` — specify the new order, preserved controls, and removed Safety item.
- Modify: `frontend/src/components/FloatingNav.tsx` — remove the forwarding Safety prop.
- Modify: `frontend/src/components/FloatingNav.test.tsx` — remove the obsolete test fixture callback.
- Modify: `frontend/src/components/MapChrome.tsx` — remove the forwarding Safety prop.
- Modify: `frontend/src/App.tsx` — remove menu Safety dialog state, import, render, and callback.
- Modify: `frontend/src/components/AppShell.test.tsx` — remove the obsolete `FloatingNav` fixture prop.
- Delete: `frontend/src/components/SafetyDialog.tsx` — no remaining consumer after the menu action disappears.
- Delete: `frontend/src/components/SafetyDialog.test.tsx` — tests only the deleted component.

### Task 1: Specify and implement the settings menu layout

**Files:**
- Modify: `frontend/src/components/NavMenu.test.tsx:9-143`
- Modify: `frontend/src/components/NavMenu.tsx:1-146`

**Interfaces:**
- Consumes: `onAbout: () => void`, `restrictionAreaMode: RestrictionAreaMode`, and `onRestrictionAreaModeChange: (mode: RestrictionAreaMode) => void` from `FloatingNav`.
- Produces: `NavMenu` without an `onSafety` prop; it renders the retained sections in DOM order: restriction area, language, Feedback, About.

- [ ] **Step 1: Write the failing menu test**

  In `NavMenu.test.tsx`, remove `onSafety` from `renderMenu()` and replace the Safety-specific expectations with this test. The ordered labels deliberately use visible menu text and no implementation-only class names.

  ```tsx
  it("orders areas, language, feedback, and about without a safety action", async () => {
    const user = userEvent.setup();
    renderMenu();

    await openMenu(user);

    const content = screen.getByRole("dialog", { name: "Menu" });
    const text = content.textContent ?? "";
    expect(text.indexOf("Restriction areas")).toBeLessThan(text.indexOf("Language"));
    expect(text.indexOf("Language")).toBeLessThan(text.indexOf("Send feedback"));
    expect(text.indexOf("Send feedback")).toBeLessThan(text.indexOf("About Highline Scout"));
    expect(screen.queryByRole("button", { name: "Safety" })).not.toBeInTheDocument();
  });
  ```

  Update the existing About, Escape, feedback, and language tests to assert menu closure or retained state using `About Highline Scout`, not `Safety`. Delete the menu Safety callback test.

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `npm test -- --run src/components/NavMenu.test.tsx`

  Expected: FAIL because the current menu renders Feedback and About before the restriction and language sections, and still renders Safety.

- [ ] **Step 3: Implement the minimal menu change**

  In `NavMenu.tsx`:

  ```tsx
  import { Info, Menu, MessageSquarePlus, X } from "lucide-react";

  interface NavMenuProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onAbout: () => void;
    restrictionAreaMode: RestrictionAreaMode;
    onRestrictionAreaModeChange: (mode: RestrictionAreaMode) => void;
  }
  ```

  Remove `onSafety` from the component parameters. Within `PopoverContent`, move the existing restriction-area `<div>` first, leave the existing language `<div>` immediately after it, then render the padded action container containing only these items:

  ```tsx
  <MenuItem
    icon={<MessageSquarePlus className="h-4 w-4" />}
    label={t("feedback")}
    hint={feedbackNoted ? t("feedbackComingSoon") : undefined}
    onClick={() => setFeedbackNoted(true)}
  />
  <MenuItem
    icon={<Info className="h-4 w-4" />}
    label={t("about")}
    onClick={() => select(onAbout)}
  />
  ```

  Preserve the existing borders between sections and do not change restriction-area or language behavior.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run: `npm test -- --run src/components/NavMenu.test.tsx`

  Expected: PASS; all menu tests pass and none reference Safety.

- [ ] **Step 5: Commit the menu layout change**

  ```bash
  git add frontend/src/components/NavMenu.tsx frontend/src/components/NavMenu.test.tsx
  git commit -m "feat(web): reorder settings menu"
  ```

### Task 2: Remove the obsolete Safety dialog wiring and files

**Files:**
- Modify: `frontend/src/components/FloatingNav.tsx:7-43`
- Modify: `frontend/src/components/FloatingNav.test.tsx:8-17`
- Modify: `frontend/src/components/MapChrome.tsx:12-38`
- Modify: `frontend/src/App.tsx:3-11,52-55,170-193`
- Modify: `frontend/src/components/AppShell.test.tsx:203-213`
- Delete: `frontend/src/components/SafetyDialog.tsx`
- Delete: `frontend/src/components/SafetyDialog.test.tsx`

**Interfaces:**
- Consumes: the Task 1 `NavMenu` API, which no longer accepts `onSafety`.
- Produces: a type-correct app that still renders `<SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />` on initial load.

- [ ] **Step 1: Write the failing integration fixture changes**

  Remove `onSafety` from the `FloatingNav` fixtures in `FloatingNav.test.tsx` and `AppShell.test.tsx`, and remove the `onSafety` mock/return value from `renderNav()`. Then run the TypeScript build before changing production callers.

- [ ] **Step 2: Run the build to verify it fails**

  Run: `npm run build`

  Expected: FAIL with TypeScript errors that `onSafety` is still required by `FloatingNav`, proving the tests and fixtures target the intended public API removal.

- [ ] **Step 3: Remove Safety forwarding, state, and files**

  Make these exact production changes:

  ```tsx
  // FloatingNav.tsx
  interface FloatingNavProps {
    onAbout: () => void;
    restrictionAreaMode?: RestrictionAreaMode;
    onRestrictionAreaModeChange?: (mode: RestrictionAreaMode) => void;
  }
  // Remove onSafety from destructuring and from <NavMenu ... />.
  ```

  ```tsx
  // MapChrome.tsx
  // Remove onSafety from MapChromeProps and delete:
  // onSafety={props.onSafety}
  ```

  ```tsx
  // App.tsx
  // Delete the SafetyDialog import, safetyOpen state, onSafety prop passed to
  // MapChrome, and <SafetyDialog open={safetyOpen} onOpenChange={setSafetyOpen} />.
  // Keep the SafetyDisclaimerDialog import, disclaimerOpen state, and render unchanged.
  ```

  Delete `SafetyDialog.tsx` and `SafetyDialog.test.tsx`. Do not delete the `safety`, `disclaimer*`, or `caveat` i18n strings because `SafetyDisclaimerDialog` still depends on the disclaimer copy.

- [ ] **Step 4: Run focused tests and the production build**

  Run: `npm test -- --run src/components/NavMenu.test.tsx src/components/FloatingNav.test.tsx src/components/AppShell.test.tsx && npm run build`

  Expected: PASS; Vitest reports all selected files passing and Vite completes a production build without TypeScript errors.

- [ ] **Step 5: Check for stale Safety dialog references**

  Run: `rg -n "SafetyDialog|onSafety" frontend/src --glob '!**/tsconfig.tsbuildinfo'`

  Expected: no output. Confirm that `rg -n "SafetyDisclaimerDialog" frontend/src` still returns its `App.tsx`, component, and test references.

- [ ] **Step 6: Commit the removal**

  ```bash
  git add frontend/src/App.tsx frontend/src/components/MapChrome.tsx frontend/src/components/FloatingNav.tsx frontend/src/components/FloatingNav.test.tsx frontend/src/components/AppShell.test.tsx frontend/src/components/SafetyDialog.tsx frontend/src/components/SafetyDialog.test.tsx
  git commit -m "refactor(web): remove menu safety dialog"
  ```
