# Lazy-load PostHog design

## Goal

Remove PostHog from the frontend's initial JavaScript chunk without changing
analytics behavior or the cookieless privacy guarantees.

## Design

`frontend/src/lib/analytics.ts` will replace its static `posthog-js` import
with a dynamic import performed only after `shouldEnableAnalytics()` accepts a
production, non-local hostname. The module will retain its existing synchronous
public event functions.

While the SDK is loading, `capture()` will retain events in an in-memory queue.
Once the import resolves, the module will initialize PostHog with the existing
options and flush the queued events in order. Calls in development and local
production previews remain no-ops, with no SDK import.

The cookieless options remain unchanged: memory persistence, always-on
cookieless mode, identified-only person profiles, and the four dashboard
features explicitly disabled.

## Verification

Tests will prove that analytics stays gated locally, that events sent during
loading flush after initialization, and that the PostHog initialization options
are unchanged. A production build will show PostHog as a separate async asset
and no longer emit Vite's 500 kB entry-chunk warning.
