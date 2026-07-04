# PostHog frontend analytics (production-only)

**Date:** 2026-07-04
**Status:** Approved

## Goal

Add product analytics to the Highline Scout web frontend so we can see how the
map is actually used (which regions people explore, which controls they touch),
**without sending any events during local development**.

## Decisions

- **Frontend-only** (`posthog-js`). Autocapture answers the "how is the tool
  used" questions with the least code. Backend/server-side capture was
  considered and rejected: the frontend is chatty (slider drags and map pans
  fire many `/zones` requests) so the backend can't see user *intent*, only a
  flood of bbox requests. Error monitoring is already handled elsewhere
  (GlitchTip).
- **Production gate = host is not localhost.** No build step exists, so the key
  cannot be baked in per-environment at build time. Instead the browser checks
  `location.hostname`: PostHog initializes on any deployed host and stays silent
  on `localhost` / loopback. This means `just dev` never sends events, and any
  future non-local deployment tracks automatically with no config.
- **Key is hard-coded in frontend source.** PostHog *project API keys*
  (`phc_...`) are write-only ingestion keys designed to live in client JS; they
  cannot read data. Not a secret. (Distinct from personal keys `phx_...`, which
  are secret and never used here.)
- **EU Cloud** — `api_host: https://eu.i.posthog.com` (EU data residency).
- **Autocapture only** — no hand-coded custom events for now.
- **`person_profiles: 'always'`** — anonymous public site with no login; this
  gives real unique-visitor counts (vs the cheaper `identified_only` default).

## Implementation

### New file `web/analytics.js`

Plain `<script>` (mirrors the no-build `i18n.js` pattern). Contains PostHog's
official loader snippet (async-loads `array.js` from
`https://eu-assets.i.posthog.com` — consistent with the page already loading
Leaflet from unpkg) followed by a guarded init:

```js
const LOCAL = ['localhost', '127.0.0.1', '::1', '0.0.0.0', ''];
if (!LOCAL.includes(location.hostname)) {
  posthog.init('phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst', {
    api_host: 'https://eu.i.posthog.com',
    person_profiles: 'always',
  });
}
```

When the guard fails on local dev, the `posthog` stub installed by the loader is
a harmless no-op, so nothing errors and nothing is sent.

### `web/index.html`

Add one line — `<script src="analytics.js"></script>` — after Leaflet loads and
**before** `i18n.js` / `app.js`, so the pageview fires as early as possible.

### Unchanged

`highliner/app.py` static mount, Python deps, and `docker-compose.yaml` all stay
as-is. No `/config` endpoint, no backend involvement.

## Out of scope (flagged, deliberately deferred)

- **Cookie-consent banner.** PostHog sets cookies; a strict GDPR reading wants
  consent first. Not requested; larger feature. Add later via PostHog's opt-in
  API if needed.
- **Custom events / funnels.** Add targeted `posthog.capture(...)` calls later
  if a specific question can't be answered from autocapture.

## Verification

- `just dev` → open `http://localhost:8000` → confirm **no** requests to
  `*.i.posthog.com` in the Network tab and `posthog` is a no-op.
- Simulate a deployed host (e.g. visit via a non-localhost hostname) → confirm a
  pageview + autocapture events reach `eu.i.posthog.com` and show in the PostHog
  Activity view.
