# Cookieless Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PostHog store nothing on the visitor's device, so no cookie consent banner is required, and disclose the anonymous analytics in the existing safety modal.

**Architecture:** Three options on the existing `posthog.init` call in `frontend/src/lib/analytics.ts` (`persistence: "memory"`, `person_profiles: "identified_only"`, `disable_session_recording: true`). No consent UI, no gating, no new component — `initAnalytics()` stays at module scope in `main.tsx`. A single new i18n string is rendered in the `SafetyDisclaimerDialog` that every visitor already sees.

**Tech Stack:** Vite + React 18 + TypeScript (strict), `posthog-js`, vitest + @testing-library/react, Tailwind.

**Spec:** `docs/superpowers/specs/2026-07-11-cookieless-analytics-design.md`

## Global Constraints

- All frontend commands run from the `frontend/` directory. Node ≥ 20.
- `npm run build` runs `tsc -b` with strict TypeScript. Test files are typechecked too — no implicit `any`.
- The i18n catalog has exactly three languages: `ca`, `es`, `en` (`LANGS` in `strings.ts:1`). The catalog-parity test at `src/lib/i18n/i18n.test.tsx:11` fails if a key is missing from any of them. Catalan is the source language.
- The PostHog write-only ingestion key `phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst` and host `https://eu.i.posthog.com` are unchanged — do not touch them.
- Do not move `initAnalytics()` out of `main.tsx`, and do not add any consent gate, banner, or preferences UI. Storing nothing on the device is what removes the consent obligation; gating it would be redundant work.
- `shouldEnableAnalytics`, `capture`, and `captureMapSettled` keep their current behaviour and signatures.

---

### Task 1: Make PostHog cookieless

**Files:**
- Modify: `frontend/src/lib/analytics.ts:25-30` (the `posthog.init` call)
- Modify: `AGENTS.md:57-62` (repo root — the Frontend bullet of the Telemetry section)
- Test: `frontend/src/lib/analytics.test.ts:54-63` (update) and a new describe block

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks depend on. `initAnalytics(isProd?: boolean, hostname?: string): void` keeps its exact current signature.

- [ ] **Step 1: Update the existing init assertion to the cookieless options**

In `frontend/src/lib/analytics.test.ts`, replace the assertion in the test `"initializes PostHog and forwards events when enabled"` (currently lines 57-60):

```ts
    expect(initMock).toHaveBeenCalledWith(
      "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst",
      {
        api_host: "https://eu.i.posthog.com",
        persistence: "memory",
        person_profiles: "identified_only",
        disable_session_recording: true,
      },
    );
```

- [ ] **Step 2: Add a test that names the compliance-critical options**

Append this describe block to the end of `frontend/src/lib/analytics.test.ts`. It exists so that deleting `persistence: "memory"` fails with a test name that says why it mattered — a future contributor is most likely to remove it while "fixing" the inflated unique-user counts.

```ts
describe("cookieless persistence", () => {
  it("stores nothing on the device, so no consent banner is required", async () => {
    const { initAnalytics } = await loadModule();
    initAnalytics(true, "highlinescout.com");

    const options = initMock.mock.calls[0]?.[1] as Record<string, unknown>;
    // No cookie, no localStorage: distinct_id lives in memory for the page's life.
    expect(options.persistence).toBe("memory");
    // We never call identify(), so no person profiles are created.
    expect(options.person_profiles).toBe("identified_only");
    // Session replay is dashboard-toggleable; pinning it off keeps DOM content
    // (which would need consent) from ever being recorded.
    expect(options.disable_session_recording).toBe(true);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run from `frontend/`: `npx vitest run src/lib/analytics.test.ts`

Expected: FAIL. The updated assertion in Step 1 reports the received object as `{ api_host: "https://eu.i.posthog.com", person_profiles: "always" }`, and the new test fails with `expected undefined to be "memory"`.

- [ ] **Step 4: Make PostHog cookieless**

In `frontend/src/lib/analytics.ts`, replace the `posthog.init(...)` call inside `initAnalytics` (currently lines 25-30) with:

```ts
  // Cookieless by design: "memory" persistence writes nothing to the device, so
  // no ePrivacy consent — and therefore no cookie banner — is required.
  // `identified_only` keeps events anonymous (we never call identify()). Session
  // replay is pinned off here because it is otherwise toggleable from the PostHog
  // dashboard, and recording DOM content would need consent.
  // The cost is cross-session identity: "users" in PostHog means "visits".
  // Do not restore `person_profiles: "always"` to fix the unique-user counts —
  // that reintroduces the consent obligation. See
  // docs/superpowers/specs/2026-07-11-cookieless-analytics-design.md
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    persistence: "memory",
    person_profiles: "identified_only",
    disable_session_recording: true,
  });
```

- [ ] **Step 5: Run the tests to verify they pass**

Run from `frontend/`: `npx vitest run src/lib/analytics.test.ts`

Expected: PASS, all tests in the file (including the pre-existing `shouldEnableAnalytics`, `capture`, and `captureMapSettled` suites, which must be unaffected).

- [ ] **Step 6: Update the AGENTS.md telemetry section**

This is the durable half of the change: the config is three lines, but the reason it must stay that way is what gets lost. In `AGENTS.md`, replace the **Frontend** bullet (lines 57-62) with:

```markdown
- **Frontend** (`frontend/src/lib/analytics.ts`) — PostHog, initialized only in a
  production build on a non-local hostname. Autocapture plus four events bound to
  committed actions: `filter_changed`, `zone_opened`, `restriction_layer_toggled`,
  and a debounced `map_settled`. Never bind analytics to a slider's
  `onValueChange` or to a raw `moveend` — those fire per drag frame, and one
  gesture would be recorded dozens of times.
- **Analytics is deliberately cookieless, and must stay that way.**
  `persistence: "memory"` writes nothing to the visitor's device and
  `person_profiles: "identified_only"` keeps events anonymous, which is why the
  app needs no cookie consent banner. The price is that there is no cross-session
  identity: **read "users" in PostHog as "visits"** — a returning visitor counts
  again each time, and retention/cohort analysis is meaningless. Restoring
  `person_profiles: "always"` would fix those counts and silently make the app
  non-compliant. Don't.
```

- [ ] **Step 7: Typecheck, then commit**

Run from `frontend/`: `npm run build`
Expected: exits 0 (`tsc -b` clean, Vite build succeeds).

```bash
git add frontend/src/lib/analytics.ts frontend/src/lib/analytics.test.ts AGENTS.md
git commit -m "feat(web): make PostHog cookieless, removing the consent obligation"
```

---

### Task 2: Disclose the anonymous analytics in the safety modal

GDPR Art. 13 still requires *telling* users what is collected even where consent is not required. The safety modal is the only screen every visitor reliably sees (`App.tsx:29` opens it on every load), so the disclosure goes there rather than in a privacy page nobody would click.

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (three catalogs: `ca` ~line 21, `es` ~line 70, `en` ~line 119)
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx:41-43` (the muted text block)
- Test: `frontend/src/components/SafetyDisclaimerDialog.test.tsx` (new test)

**Interfaces:**
- Consumes: nothing from Task 1. The two tasks are independent and may be done in either order.
- Produces: a new `StringKey`, `disclaimerPrivacy`. `StringKey` is derived from the catalog object, so no type declaration needs editing by hand.

- [ ] **Step 1: Write the failing test**

Append to the `describe("SafetyDisclaimerDialog", ...)` block in `frontend/src/components/SafetyDisclaimerDialog.test.tsx`. The regex spans all three languages, matching the pattern the existing tests in this file already use for the accept button.

```tsx
  it("discloses the anonymous, cookieless analytics", () => {
    render(
      <I18nProvider>
        <SafetyDisclaimerDialog open onAccept={vi.fn()} />
      </I18nProvider>,
    );

    expect(screen.getByText(/sense galetes|sin cookies|no cookies/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `frontend/`: `npx vitest run src/components/SafetyDisclaimerDialog.test.tsx`

Expected: FAIL with `Unable to find an element with the text: /sense galetes|sin cookies|no cookies/i`.

- [ ] **Step 3: Add the string to all three catalogs**

In `frontend/src/lib/i18n/strings.ts`, add `disclaimerPrivacy` immediately after `disclaimerResponsibility` in each catalog. Catalan (after line 21):

```ts
    disclaimerPrivacy:
      "Recollim estadístiques d'ús anònimes per millorar l'eina. Sense galetes ni seguiment entre visites.",
```

Spanish (after line 70):

```ts
    disclaimerPrivacy:
      "Recogemos estadísticas de uso anónimas para mejorar la herramienta. Sin cookies ni seguimiento entre visitas.",
```

English (after line 119):

```ts
    disclaimerPrivacy:
      "We collect anonymous usage stats to improve the tool. No cookies, no tracking across visits.",
```

- [ ] **Step 4: Render it in the dialog**

In `frontend/src/components/SafetyDisclaimerDialog.tsx`, replace the muted text block (lines 41-43) with the version below. The `text-xs` keeps the privacy line visually subordinate — it must not compete with the safety warning, which is the actual point of this dialog.

```tsx
          <div className="space-y-3 text-sm text-muted-foreground">
            <p className="font-semibold text-destructive">{t("disclaimerLead")}</p>
            <p>{t("disclaimerBody")}</p>
            <p>{t("disclaimerResponsibility")}</p>
            <p className="text-xs">{t("disclaimerPrivacy")}</p>
          </div>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run from `frontend/`: `npx vitest run src/components/SafetyDisclaimerDialog.test.tsx src/lib/i18n/i18n.test.tsx`

Expected: PASS. The i18n catalog-parity test confirms all three languages carry the new key; it fails here if one was missed.

- [ ] **Step 6: Run the full frontend suite and typecheck**

Run from `frontend/`: `npm test && npm run build`
Expected: all vitest suites pass, `tsc -b` exits 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/components/SafetyDisclaimerDialog.tsx frontend/src/components/SafetyDisclaimerDialog.test.tsx
git commit -m "feat(web): disclose anonymous cookieless analytics in the safety modal"
```

---

## Verification

After both tasks, from `frontend/`:

- `npm test` — full vitest suite green, including `App.analytics.test.tsx`, which exercises the four committed events and must be unaffected by the persistence change.
- `npm run build` — strict typecheck + production build clean.

Manual check that the app stores nothing (the whole point of the change), since the unit tests only assert the options passed to `posthog.init`:

1. `npm run build && npm run preview`, open the previewed URL.
2. `shouldEnableAnalytics` returns `false` on localhost, so **PostHog will not initialize in preview** — this is expected and is why the manual check cannot be done locally without a temporary override. To exercise it, call `initAnalytics(true, "highlinescout.com")` from the browser console, interact with the map, then confirm in DevTools → Application that **no `ph_*` cookie and no `ph_*` localStorage entry** exists for the origin.
3. Revert any temporary override before committing.

## Not doing

Per the spec: no consent banner, no cookie preferences UI, no consent-management library, no separate privacy page, no backend change (`highliner/core/telemetry.py` already emits anonymous system events under a fixed `SERVER_DISTINCT_ID` and forwards no client identity).
