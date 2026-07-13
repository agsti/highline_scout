# Lazy-load PostHog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove PostHog from the initial frontend bundle while preserving production analytics events and cookieless privacy guarantees.

**Architecture:** `analytics.ts` will dynamically import `posthog-js` only after the existing production/non-local gate passes. It exposes the same synchronous event-capture API to the UI, buffering events while the SDK initializes and flushing them in order once it is ready. The entry point starts initialization without delaying the first render.

**Tech Stack:** TypeScript, React 18, Vite 6, Vitest 2, PostHog JS.

## Global Constraints

- Preserve `persistence: "memory"`, `cookieless_mode: "always"`, `person_profiles: "identified_only"`, and all four `disable_*` privacy flags unchanged.
- Do not import `posthog-js` statically from any frontend source file.
- Development builds and local production previews must not load PostHog or record events.
- Keep `capture(event, properties?)` synchronous for all existing UI call sites.
- Keep code within the repository's strict TypeScript and frontend-test conventions.

---

### Task 1: Make analytics initialization lazy and lossless

**Files:**
- Modify: `frontend/src/lib/analytics.ts:1-76`
- Modify: `frontend/src/lib/analytics.test.ts:1-112`
- Modify: `frontend/src/main.tsx:5,8`

**Interfaces:**
- Consumes: `shouldEnableAnalytics(isProd: boolean, hostname: string): boolean`.
- Produces: `initAnalytics(isProd?: boolean, hostname?: string): Promise<void>` and unchanged `capture(event: string, properties?: Record<string, unknown>): void`.
- Produces: an in-memory FIFO queue of `[event, properties]` tuples used only while the SDK import is in progress.

- [ ] **Step 1: Write the failing tests for lazy initialization and queued events**

In `frontend/src/lib/analytics.test.ts`, retain the `vi.mock("posthog-js", ...)` factory returning `initMock` and `captureMock`. Add a deferred-import test seam by mocking a new `loadPosthog` helper exported only from `analytics-loader.ts`. Then add:

```ts
it("loads PostHog only after the production gate passes", async () => {
  const { initAnalytics } = await loadModule();

  await initAnalytics(true, "highlinescout.com");

  expect(initMock).toHaveBeenCalledWith(
    "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst",
    expect.objectContaining({
      persistence: "memory",
      cookieless_mode: "always",
      person_profiles: "identified_only",
      disable_session_recording: true,
      disable_surveys: true,
      disable_product_tours: true,
      disable_conversations: true,
    }),
  );
});

it("flushes events captured while PostHog is loading in order", async () => {
  let resolveLoader: (() => void) | undefined;
  loadPosthogMock.mockImplementationOnce(
    () => new Promise((resolve) => { resolveLoader = () => resolve(posthog); }),
  );
  const { capture, initAnalytics } = await loadModule();

  const initializing = initAnalytics(true, "highlinescout.com");
  capture("filter_changed", { min_len: 20 });
  capture("zone_opened", { n_pairs: 3 });
  expect(captureMock).not.toHaveBeenCalled();

  resolveLoader?.();
  await initializing;
  expect(captureMock.mock.calls).toEqual([
    ["filter_changed", { min_len: 20 }],
    ["zone_opened", { n_pairs: 3 }],
  ]);
});
```

Define `posthog` in the test as `{ init: initMock, capture: captureMock }` and reset `loadPosthogMock` in `beforeEach`.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- src/lib/analytics.test.ts`

Expected: FAIL because no `analytics-loader.ts` module or asynchronous initializer exists yet.

- [ ] **Step 3: Add a focused dynamic-import boundary**

Create `frontend/src/lib/analytics-loader.ts`:

```ts
import type posthog from "posthog-js";

export function loadPosthog(): Promise<typeof posthog> {
  return import("posthog-js").then(({ default: client }) => client);
}
```

This keeps the dynamic import in one mockable module and guarantees Vite creates an async PostHog chunk.

- [ ] **Step 4: Implement the dynamic loader and queue**

In `frontend/src/lib/analytics.ts`, remove the static PostHog import. Add:

```ts
import type posthog from "posthog-js";
import { loadPosthog } from "./analytics-loader";

type AnalyticsEvent = [event: string, properties?: Record<string, unknown>];
type PosthogClient = typeof posthog;

let client: PosthogClient | undefined;
let loading: Promise<void> | undefined;
let queuedEvents: AnalyticsEvent[] = [];
```

Move the existing unchanged `posthog.init(POSTHOG_KEY, { ... })` options into:

```ts
async function loadAnalytics(): Promise<void> {
  const posthog = await loadPosthog();
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    persistence: "memory",
    cookieless_mode: "always",
    person_profiles: "identified_only",
    disable_session_recording: true,
    disable_surveys: true,
    disable_product_tours: true,
    disable_conversations: true,
  });
  client = posthog;
  for (const [event, properties] of queuedEvents) posthog.capture(event, properties);
  queuedEvents = [];
}
```

Change the initializer and capture function to:

```ts
export function initAnalytics(
  isProd: boolean = import.meta.env.PROD,
  hostname: string = window.location.hostname,
): Promise<void> {
  if (!shouldEnableAnalytics(isProd, hostname)) return Promise.resolve();
  loading ??= loadAnalytics();
  return loading;
}

export function capture(event: string, properties?: Record<string, unknown>): void {
  if (client) {
    client.capture(event, properties);
  } else if (loading) {
    queuedEvents.push([event, properties]);
  }
}
```

In `frontend/src/main.tsx`, replace `initAnalytics();` with `void initAnalytics();` to start the async work without blocking React's initial render.

- [ ] **Step 5: Run the focused analytics tests to verify they pass**

Run: `npm test -- src/lib/analytics.test.ts`

Expected: PASS. The existing gated/no-op, configuration, and debounce tests remain green; the new tests prove the delayed SDK load and FIFO event flush.

- [ ] **Step 6: Run the full frontend test suite**

Run: `npm test`

Expected: PASS with no Vitest failures.

- [ ] **Step 7: Commit the implementation**

```bash
git add frontend/src/lib/analytics.ts frontend/src/lib/analytics-loader.ts frontend/src/lib/analytics.test.ts frontend/src/main.tsx
git commit -m "perf: lazy-load PostHog analytics"
```

### Task 2: Verify the production bundle outcome

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: the dynamic `import("posthog-js")` in `analytics-loader.ts`.
- Produces: a production build with a separate PostHog async asset and an entry chunk below Vite's 500 kB warning threshold.

- [ ] **Step 1: Build the frontend from a clean output directory**

Run: `rm -rf dist && npm run build`

Expected: TypeScript succeeds, Vite emits a distinct async JavaScript asset for PostHog, and the output contains no `Some chunks are larger than 500 kB` warning.

- [ ] **Step 2: Inspect emitted assets**

Run: `find dist/assets -maxdepth 1 -type f -printf '%f %s bytes\n' | sort`

Expected: the main `index-*.js` is below 500,000 bytes minified and a separate JavaScript asset contains the PostHog code. Do not raise `chunkSizeWarningLimit` or add `manualChunks`.

- [ ] **Step 3: Confirm the working tree contains only intended changes**

Run: `git status --short`

Expected: no changed tracked files beyond the Task 1 implementation and plan, while pre-existing untracked user files remain untouched.
