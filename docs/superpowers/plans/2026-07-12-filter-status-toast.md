# Filter Status Toast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove result/loading statuses from both responsive filter surfaces and show request failures in a temporary map-level toast.

**Architecture:** Add a focused `ErrorToast` presentation component with its own dismissal timer. Keep `MapView`'s informational status callback for its existing internal/test contract, add a dedicated error callback, and have `App` route all map/anchor/restriction failures into the toast while `MapChrome` stops accepting status content.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Vitest, Testing Library

## Global Constraints

- The desktop filters panel and mobile controls sheet render no map, anchor, restriction, loading, or successful-result status lines.
- Successful zone and anchor counts are not shown elsewhere.
- Map, anchor, restriction-layer, and restriction-metadata failures share one temporary toast layered over the map.
- A newer error replaces the visible error; every reported error starts a fresh 5000 ms dismissal interval.
- The toast uses `role="alert"` and must not block map interaction.
- Existing map loading spinner behavior remains unchanged.
- Do not add a toast dependency.

---

### Task 1: Accessible Temporary Error Toast

**Files:**
- Create: `frontend/src/components/ErrorToast.tsx`
- Create: `frontend/src/components/ErrorToast.test.tsx`

**Interfaces:**
- Consumes: `message: string`, `eventId: number`, and `onDismiss: () => void` props.
- Produces: `ERROR_TOAST_MS = 5000` and `ErrorToast` for `MapChrome` integration.

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/ErrorToast.test.tsx` with fake-timer tests that render `<ErrorToast message="Could not load zones" eventId={1} onDismiss={onDismiss} />`, assert `screen.getByRole("alert")` contains the message, advance by `ERROR_TOAST_MS`, and assert `onDismiss` was called once. Add a rerender test that advances part of the interval, rerenders with `message="Could not load anchors" eventId={2}`, advances to just before the new interval and asserts no dismissal, then advances the final millisecond and asserts one dismissal.

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd frontend && npm test -- src/components/ErrorToast.test.tsx`

Expected: FAIL because `./ErrorToast` does not exist.

- [ ] **Step 3: Implement the minimal toast**

Create `frontend/src/components/ErrorToast.tsx`:

```tsx
import { useEffect } from "react";

export const ERROR_TOAST_MS = 5000;

interface ErrorToastProps {
  message: string;
  eventId: number;
  onDismiss: () => void;
}

export function ErrorToast({ message, eventId, onDismiss }: ErrorToastProps) {
  useEffect(() => {
    if (!message) return;
    const timeout = window.setTimeout(onDismiss, ERROR_TOAST_MS);
    return () => window.clearTimeout(timeout);
  }, [message, eventId, onDismiss]);

  if (!message) return null;

  return (
    <div
      role="alert"
      className="pointer-events-none absolute left-1/2 top-[78px] z-[1100] max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-lg bg-destructive px-4 py-2 text-center text-sm font-semibold text-destructive-foreground shadow-lg"
    >
      {message}
    </div>
  );
}
```

- [ ] **Step 4: Verify GREEN**

Run: `cd frontend && npm test -- src/components/ErrorToast.test.tsx`

Expected: 2 tests pass with no warnings.

- [ ] **Step 5: Commit Task 1**

```bash
git add frontend/src/components/ErrorToast.tsx frontend/src/components/ErrorToast.test.tsx
git commit -m "feat(web): add temporary error toast"
```

---

### Task 2: Route Errors to the Toast and Remove Filter Statuses

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/components/map/MapView.test.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/components/FiltersPanel.tsx`
- Modify: `frontend/src/components/FiltersPanel.test.tsx`
- Modify: `frontend/src/components/MobileControlSheet.tsx`
- Modify: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: Task 1's `ErrorToast({ message, eventId, onDismiss })`.
- Produces: optional `MapViewProps.onError?: (message: string) => void`; optional legacy informational callbacks; `MapChromeProps.errorMessage: string`, `errorEventId: number`, and `onErrorDismiss: () => void`; status-free `FiltersPanel` and `MobileControlSheet` APIs.

- [ ] **Step 1: Write failing responsive and application tests**

Update `FiltersPanel.test.tsx` so its helper passes no `statuses` prop and the collapse test only asserts filter content. Update `AppShell.test.tsx`/its `MapChrome` or sheet fixtures to stop supplying `statuses` where TypeScript requires the removed API.

In `App.test.tsx`, extend the `MapView` mock to capture both `onMapStatus` and `onError`. Replace `shows the map status in the chrome` with a test asserting `queryByText("3 zones")` is absent after the mock publishes it. Import `ErrorToast` and update the existing `MapChrome` mock to render it from the received `errorMessage`, `errorEventId`, and `onErrorDismiss` props. Add a test that publishes `onError?.("Error: zones unavailable")`, asserts `getByRole("alert")` contains that text, advances fake timers by 5000 ms, and asserts the alert is gone. Add a restriction-metadata test that rejects `fetchRestrictionLayers` with `{ name: "RequestError", detail: "metadata unavailable" }` and asserts the localized error appears in the same alert.

In `MapView.test.tsx`, add `onError={props?.onError ?? vi.fn()}` to the standard render helper. Add three focused tests: reject `fetchZones` with `new Error("zones unavailable")` and expect `onError` to receive `"Error: zones unavailable"`; reject `fetchAnchors` with `new Error("anchors unavailable")` and expect `"Error carregant ancoratges: anchors unavailable"`; enable `zepa`, reject `fetchRestrictions` with `new Error("restrictions unavailable")`, and expect `"Error: restrictions unavailable"`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd frontend && npm test -- src/App.test.tsx src/components/FiltersPanel.test.tsx src/components/AppShell.test.tsx src/components/map/MapView.test.tsx`

Expected: FAIL because the status props still render and `MapView` has no `onError` callback.

- [ ] **Step 3: Add the dedicated map error channel**

In `MapView.tsx`, make `onMapStatus`, `onAnchorStatus`, and `onRestrictionStatus` optional and invoke them with optional chaining. Add optional `onError?: (message: string) => void`. In each non-413 catch path, compute the already-localized message once, continue publishing it through the matching legacy status callback, and call `onError?.(message)`. Cover zone/density errors, anchor errors, and restriction errors. Do not toast 413 zoom guidance because it is not a failure.

- [ ] **Step 4: Integrate shared error state in App and MapChrome**

In `App.tsx`, remove `mapStatus`, `mapErrorDetail`, `anchorStatus`, `restrictionStatus`, the `statuses` React node, and the `StatusLine` import. Add state shaped as `{ id: number; message: string } | null` and a stable callback that sets `{ id: (previous?.id ?? 0) + 1, message }` for every error. Use it for `MapView.onError` and for `fetchRestrictionLayers` failures. Stop passing the three informational callbacks. Pass `errorMessage={error?.message ?? ""}`, `errorEventId={error?.id ?? 0}`, and `onErrorDismiss={() => setError(null)}` to `MapChrome`.

In `MapChrome.tsx`, render:

```tsx
<ErrorToast
  message={props.errorMessage}
  eventId={props.errorEventId}
  onDismiss={props.onErrorDismiss}
/>
```

Remove `statuses` from `MapChromeProps`, both responsive child calls, `FiltersPanelProps`, and `MobileControlSheetProps`, then remove the rendered status nodes from both filter surfaces.

- [ ] **Step 5: Verify focused tests GREEN**

Run: `cd frontend && npm test -- src/components/ErrorToast.test.tsx src/App.test.tsx src/components/FiltersPanel.test.tsx src/components/AppShell.test.tsx src/components/map/MapView.test.tsx`

Expected: all selected tests pass with no warnings.

- [ ] **Step 6: Verify the complete frontend**

Run: `cd frontend && npm test`

Expected: all Vitest tests pass.

Run: `cd frontend && npm run build`

Expected: TypeScript and Vite production build exit 0.

- [ ] **Step 7: Commit Task 2**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx frontend/src/components/MapChrome.tsx frontend/src/components/FiltersPanel.tsx frontend/src/components/FiltersPanel.test.tsx frontend/src/components/MobileControlSheet.tsx frontend/src/components/AppShell.test.tsx
git commit -m "fix(web): move filter errors to map toast"
```
