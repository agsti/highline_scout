# Cookieless analytics (no consent banner)

**Date:** 2026-07-11
**Status:** Approved
**Amends:** `2026-07-11-posthog-analytics-design.md`

## Context

The request was "add a cookie consent banner". Investigating what would need
consenting to turned up a better answer: remove the thing that needs consent.

Today `initAnalytics()` runs at module scope in `main.tsx` and calls
`posthog.init(..., { person_profiles: "always" })`. With default persistence,
PostHog writes a cookie and a `localStorage` entry, and creates a person
profile, **before the user has any say**. The app serves Catalonia from
`eu.i.posthog.com`, so GDPR/ePrivacy applies for real, and a banner that merely
*informs* ("we use cookies, OK") would not be compliant — consent must gate the
tracking, and rejecting must be as easy as accepting.

A compliant consent gate was the alternative. It was rejected: it would stack a
second interruption on top of `SafetyDisclaimerDialog` (which already blocks
every load and is not persisted), and realistically 40–70% of analytics volume
would be lost to rejections and banner-ignorers.

Storing nothing on the device sidesteps the consent obligation altogether. No
banner is built.

## Decisions

- **PostHog persists nothing on the device.** `persistence: "memory"` — no
  cookie, no `localStorage`. `distinct_id` lives in memory for the page's life.
  This is the option that removes the ePrivacy consent trigger; everything else
  here is secondary.
- **Same-day unique visitors are recovered via `cookieless_mode: "always"`.**
  Instead of a client-held `distinct_id`, every event carries a
  `$posthog_cookieless` sentinel; PostHog's server hashes IP + User-Agent + a
  salt that rotates daily into a visitor ID, stable across that visitor's
  events for the day, changing the next. This recovers same-day unique-visitor
  counts while writing nothing to the device. It is layered on top of
  `persistence: "memory"`, not a substitute for it: `cookieless_mode` disables
  PostHog's persistence I/O (load/save/remove all become no-ops), but
  `persistence: "memory"` independently governs which storage backend gets
  *constructed* — including in the brief pre-disable window during `init()`
  and for the explicit `remove()`/cookie-expiry calls disabling triggers — so
  those paths only ever touch a plain in-process object. Keep both; they are
  complementary, not redundant. Cross-*day* identity is still lost — a
  visitor's hashed ID changes daily, so retention/cohort analysis spanning days
  remains meaningless. (PostHog's project settings must also have cookieless
  mode enabled server-side, or cookieless events are dropped at ingestion —
  this is a dashboard setting, out of scope for this repo.)
- **Events are anonymous.** `person_profiles: "identified_only"`. The code never
  calls `posthog.identify()`, so no person profiles are created. (Also cheaper
  on PostHog's anonymous-event pricing.)
- **Session recording is pinned off in code.** `disable_session_recording: true`.
  Session replay is toggled *server-side* in the PostHog dashboard; without this
  it could be switched on there and silently begin recording DOM content, which
  would unambiguously require consent. The code must not be overridable from the
  dashboard on this point.
- **IP is kept.** PostHog still receives the visitor IP and does geo-IP lookup.
  The audience-measurement consent exemption does not require dropping it, and
  country/region geo is useful for a Catalonia-focused tool (how much scouting
  interest comes from abroad?). This is the one grey area in the pattern; if it
  is ever revisited, the change is a `before_send` hook nulling `$ip`.
- **`initAnalytics()` stays at module scope in `main.tsx`.** With nothing to
  consent to, there is nothing to gate. Not moving it is the point of the whole
  approach.
- **Disclosure lives in the safety modal.** GDPR Art. 13 still requires *telling*
  users what is collected even where consent is not required. One muted line in
  `SafetyDisclaimerDialog` — the only screen every visitor reliably sees —
  rather than a new privacy component nobody would click.

## Cost: goal 2 of the previous spec is partly sacrificed

`2026-07-11-posthog-analytics-design.md` listed as goal 2: *"Traffic & reach —
visitors, sessions, referrers."* Cookieless persistence damages this; adding
`cookieless_mode: "always"` claws back same-day unique-visitor counts, but the
remaining tradeoff is accepted deliberately:

| Still works | Broken |
|---|---|
| Event counts, trends, property breakdowns | Any funnel or analysis spanning multiple days |
| Autocapture, referrers | Retention and cohort analysis (inherently cross-day) |
| Within-session funnels | |
| **Same-day unique-visitor counts** (server-hashed, daily-rotating ID) | |

The four committed events (`filter_changed`, `zone_opened`,
`restriction_layer_toggled`, `map_settled`) are all within-session behaviours
and are unaffected. What's lost is narrower than the previous cut: a returning
visitor is no longer double-counted *within a day*, but their hashed ID changes
every day, so anything that needs to recognize the same visitor across days —
retention, cohorts, multi-day funnels — is still meaningless.

## Changes

**`frontend/src/lib/analytics.ts`** — the `posthog.init` options become:

```ts
posthog.init(POSTHOG_KEY, {
  api_host: POSTHOG_HOST,
  persistence: "memory",
  person_profiles: "identified_only",
  disable_session_recording: true,
});
```

`shouldEnableAnalytics`, `capture`, and `captureMapSettled` are untouched.

**`frontend/src/lib/i18n/strings.ts`** — one new key, `disclaimerPrivacy`, in
all three catalogs (ca/es/en). English: *"We collect anonymous usage stats to
improve the tool. No cookies, no tracking across visits."*

**`frontend/src/components/SafetyDisclaimerDialog.tsx`** — render
`disclaimerPrivacy` as a small muted `<p>` after `disclaimerResponsibility`,
visually subordinate so it does not compete with the safety warning itself.

**`AGENTS.md`** — the Telemetry section states that analytics is deliberately
cookieless and anonymous, and why. This is the durable part of the change: the
config is three lines, but the *reason it must stay that way* is what gets lost.
Switching `persistence` back to `localStorage+cookie` is precisely what a
future contributor would restore to "fix" the inflated unique-user counts,
silently reintroducing the cookie and the consent obligation. (`person_profiles:
"always"` would not even fix the counts — with `persistence: "memory"` the
`distinct_id` is regenerated every page load regardless — it would just mint a
person profile per pageview.)

## Testing

- `analytics.test.ts` — update the existing `init` assertion; add a test that
  names `persistence: "memory"` explicitly, so tidying it away fails loudly.
  This option is load-bearing for compliance and deserves a test that says so.
- `SafetyDisclaimerDialog.test.tsx` — assert the privacy line renders.
- `i18n.test.tsx` — the existing catalog-parity test already fails if any of the
  three languages is missing the new key. No new test needed.

## Not doing

- No consent banner, no cookie preferences UI, no consent-management library.
- No separate privacy page or dialog.
- No backend change. `highliner/core/telemetry.py` emits anonymous system events
  only (`slow_request`) and sets no user identity, so it is already consent-free.
