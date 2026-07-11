# PostHog analytics: frontend restore + thin backend telemetry

**Date:** 2026-07-11
**Status:** Approved
**Supersedes:** `2026-07-04-posthog-frontend-analytics-design.md`

## Context

The 2026-07-04 spec added PostHog to the old no-build static frontend
(`web/analytics.js`, commit `c6b4785`). Commit `c731d26` ("remove old static
frontend") deleted `web/` when the Vite/React app replaced it, and
`analytics.js` went with it. **The app currently has no analytics at all** — no
`posthog-js` in `frontend/package.json`, no init in `main.tsx`.

Separately, the 2026-07-04 spec asserted backend errors were "already handled
elsewhere (GlitchTip)". A self-hosted GlitchTip does exist on the VPS
(`glitch.vps.agustibau.com`), but highliner is not wired to it: no `sentry_sdk`
dependency or init exists in this repository, and its compose service sets no
DSN. A `/zones` 500 in production is currently invisible.

## Goals

1. Is the tool usable — which controls people touch, whether they reach a zone.
2. Traffic & reach — visitors, sessions, referrers.
3. Where people scout — which areas of the map get explored.
4. Backend health — slow endpoints and server errors.

Goals 1–3 are about user *intent*, which exists only in the browser. Goal 4 is
the only one that needs the server.

## Decisions

- **Frontend carries goals 1–3.** The backend sees only viewport reads; a slider
  drag or map pan fires many `/zones` bbox requests, so server-side events would
  record traffic, not intent. This is the same conclusion the 2026-07-04 spec
  reached and it still holds.
- **Backend carries goal 4 only, and emits no per-request events.** One
  threshold-triggered `slow_request` event. Errors go to GlitchTip via
  `sentry_sdk`, not to PostHog, so nothing is double-counted.
- **Backend events are anonymous system events.** No frontend `distinct_id` is
  forwarded; no client/server person stitching. Answers "is `/zones` slow", not
  "was it slow for *this* user". Avoids header plumbing and identity-linked
  server logs.
- **Disabled-by-default off production.** Frontend gates on the Vite build flag;
  backend gates on the presence of a configured key. Neither sends events during
  `just dev`.
- **Project API key stays hard-coded in frontend source.** `phc_...` keys are
  write-only ingestion keys designed to live in client JS; they cannot read
  data. Carried forward from the 2026-07-04 spec.
- **EU Cloud** (`https://eu.i.posthog.com`) and **`person_profiles: 'always'`**
  carried forward unchanged.

## Frontend

### `frontend/package.json`

Add `posthog-js`.

### New `frontend/src/lib/analytics.ts`

Exports `initAnalytics()` and a `capture(event, properties?)` wrapper that
**no-ops when PostHog was never initialized**, so tests and local dev need no
PostHog and no conditionals at the call sites.

The production gate is `import.meta.env.PROD && !isLocalHost()`. The 2026-07-04
spec gated on `location.hostname` alone *because the no-build static site could
not bake in per-environment config*; Vite has a build step, so `PROD` is now the
primary gate. The hostname check is retained as a second latch so a local
`npm run build` + `vite preview` stays silent.

Init config: the existing `phc_...` key, `api_host: 'https://eu.i.posthog.com'`,
`person_profiles: 'always'`, autocapture left on.

### `frontend/src/main.tsx`

Call `initAnalytics()` before `createRoot(...).render(...)`.

### Custom events

Autocapture covers goals 1 and 2. Four hand-written events cover the rest. Every
one is bound to a **discrete, committed** action — never to a drag or a raw pan.

| Event | Trigger | Properties |
|---|---|---|
| `filter_changed` | `onMaxLenCommit` / `onMinExposureCommit` | `filter`, `value` |
| `zone_opened` | zone popup opens | `length_min`, `length_max`, `height_max`, `n_pairs` |
| `restriction_layer_toggled` | layer checkbox | `layer`, `enabled` |
| `map_settled` | ~2s debounce after pan/zoom stops | `zoom`, `lat`, `lon` |

`App.tsx` already separates `onMaxLenCommit` from `onMaxLenChange`, so
`filter_changed` structurally cannot fire per drag frame. `map_settled` is the
goal-3 signal; the debounce is what keeps it from becoming the per-pan flood.

## Backend

### Dependencies (`pyproject.toml`)

Add `posthog` and `sentry-sdk[fastapi]`. Add a `posthog.*` entry to the mypy
`ignore_missing_imports` overrides **only if** strict mypy reports it missing —
confirm, do not assume.

### `highliner/core/config.py`

Extend `Settings` (existing `HIGHLINER_` env prefix):

| Field | Default | Purpose |
|---|---|---|
| `posthog_key` | `None` | Absent ⇒ backend telemetry disabled |
| `posthog_host` | `https://eu.i.posthog.com` | EU residency |
| `sentry_dsn` | `None` | Absent ⇒ Sentry disabled |
| `environment` | `development` | Event/error tagging |
| `slow_request_ms` | `1000` | `slow_request` threshold |

Absent credentials mean disabled, so local dev is silent by default and there is
no separate dev/prod branch to get wrong.

### New `highliner/core/telemetry.py`

Cross-cutting, so `core/` per the existing layering.

- `init_sentry(settings)` — no-op unless `sentry_dsn` is set. Starlette/FastAPI
  integration, `environment` tag, and `traces_sample_rate=0` — errors are the
  point, and tracing a per-pan endpoint would flood the self-hosted GlitchTip
  (see Deployment).
- `init_posthog(settings)` — no-op unless `posthog_key` is set.
- `SlowRequestMiddleware` — times each request; emits **only** when the duration
  exceeds `slow_request_ms`:
  - event `slow_request`
  - `distinct_id="server"` (constant), plus `$process_person_profile: False` so
    these events create no PostHog person and never pollute frontend
    unique-visitor counts
  - properties: route **template** (`/zones`, never the raw path — bbox query
    strings stay server-side), `method`, `status_code`, `duration_ms`,
    `environment`
- `shutdown_telemetry()` — calls `posthog.shutdown()` to flush the queue.

The middleware emits no error events; unhandled exceptions reach GlitchTip via
Sentry.

### `highliner/app.py`

In `create_app()`: call the two inits, add `SlowRequestMiddleware`, and register
`shutdown_telemetry()` on app shutdown.

## Deployment

Production is `highlinescout.com`, served from
`~/projects/vps/highliner/docker-compose.yaml` (a **separate repository** —
that edit lands outside this repo, as its own commit).

GlitchTip is self-hosted at `https://glitch.vps.agustibau.com`.

`gplay_scrap` puts its ingestion DSN in compose as a plain env var, but **we do
not follow that precedent**: both credentials go through sops+age like every
other service's env vars. They are write-only ingestion credentials rather than
true secrets, so this is defence-in-depth, not a strict requirement — but it
keeps one uniform way of handling credentials on the VPS.

New `~/projects/vps/highliner/secrets.enc.env` (sops+age, dotenv):

    HIGHLINER_POSTHOG_KEY=phc_...           # same project key as the frontend
    HIGHLINER_SENTRY_DSN=https://...@glitch.vps.agustibau.com/N

Encryption needs only the age **public** key, which `.sops.yaml` already pins, so
the file can be created without the private key. The deploy workflow decrypts
every `*/secrets.enc.env` to `secrets.env` using the `SOPS_AGE_KEY` repo secret.

`docker-compose.yaml` gains `env_file: [./secrets.env]` on the `highliner`
service, and `HIGHLINER_ENVIRONMENT: production` in the existing `environment:`
block alongside `HIGHLINER_DATA_DIR` — it names the deployment, it is not a
credential, so it stays in the clear.

**Blocked on the operator:** a GlitchTip project for highliner must be created to
obtain `N` and the DSN. Project `/1` belongs to `gplay_scrap`. Because
`sentry_dsn` is optional and absent-means-disabled, everything builds, tests, and
deploys green before the DSN exists; adding it later is an edit to the encrypted
file alone.

Note the env-var names differ from `gplay_scrap`'s (`GLITCHTIP_DSN` etc.) because
highliner's `Settings` uses the `HIGHLINER_` prefix throughout; that convention
wins inside this app.

`traces_sample_rate=0` deliberately diverges from `gplay_scrap`'s `1`: `/zones`
fires on every map pan and slider commit, so full tracing would flood the
self-hosted instance with transactions that add nothing over the `slow_request`
event.

## Testing

**Backend** (pytest): with a fake capture callable — a fast handler emits
nothing; a slow handler emits exactly one `slow_request` carrying the route
template and duration; with no `posthog_key`/`sentry_dsn` configured, telemetry
is inert and performs no network IO.

**Frontend** (vitest): `capture()` no-ops when uninitialized; a slider *commit*
fires exactly one `filter_changed` and a drag fires none.

## Verification

- `just test`, `just test-web`, strict mypy all green.
- `just dev` + `just dev-web` → no requests to `*.i.posthog.com` in the Network
  tab, and no PostHog/Sentry traffic from the server.
- Deployed host → autocapture pageview plus the custom events appear in PostHog
  Activity; an induced slow request produces one `slow_request` with no
  associated person.

## Out of scope (deliberate)

- **Cookie-consent banner.** PostHog sets cookies and a strict GDPR reading wants
  consent first. Deferred by the 2026-07-04 spec and still deferred — but this is
  an EU-hosted project with a primarily Catalan audience, so this is a conscious
  "not yet", not an oversight. Add via PostHog's opt-in API when needed.
- **Client/server person stitching.** Explicitly rejected above.
- **Per-request backend events, funnels, APM/Prometheus.** YAGNI.
