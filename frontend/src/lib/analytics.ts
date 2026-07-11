import posthog from "posthog-js";

// Write-only ingestion key: it can send events but cannot read data, so it is
// safe in client source. (Personal keys, phx_..., are secret and unused here.)
const POSTHOG_KEY = "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst";
const POSTHOG_HOST = "https://eu.i.posthog.com";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]);

export const MAP_SETTLED_DEBOUNCE_MS = 2000;

let enabled = false;
let mapSettledTimer: ReturnType<typeof setTimeout> | undefined;

// The dev-build check is the real gate; the hostname check additionally keeps a
// local `npm run build` + `vite preview` silent.
export function shouldEnableAnalytics(isProd: boolean, hostname: string): boolean {
  return isProd && !LOCAL_HOSTS.has(hostname);
}

export function initAnalytics(
  isProd: boolean = import.meta.env.PROD,
  hostname: string = window.location.hostname,
): void {
  if (!shouldEnableAnalytics(isProd, hostname)) return;
  // Cookieless by design: "memory" persistence writes nothing to the device, so
  // no ePrivacy consent — and therefore no cookie banner — is required.
  // `identified_only` keeps events anonymous (we never call identify()).
  // The cost is cross-session identity: "users" in PostHog means "visits". Do
  // not "fix" that by switching `persistence` back to localStorage+cookie —
  // that reintroduces the cookie and the consent obligation. (Restoring
  // `person_profiles: "always"` would not even fix the counts; it would just
  // mint a person profile per pageview.) See
  // docs/superpowers/specs/2026-07-11-cookieless-analytics-design.md
  //
  // The four `disable_*` flags below are all pinned off in code because each
  // is independently toggleable from the PostHog dashboard and, if enabled,
  // writes to the device (session recording: DOM content; the other three:
  // raw localStorage keys) with no code change and no failing test.
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    persistence: "memory",
    person_profiles: "identified_only",
    disable_session_recording: true,
    disable_surveys: true,
    disable_product_tours: true,
    disable_conversations: true,
  });
  enabled = true;
}

export function capture(event: string, properties?: Record<string, unknown>): void {
  if (!enabled) return;
  posthog.capture(event, properties);
}

// Panning fires `moveend` per gesture; debouncing collapses a scroll across the
// map into the one viewport the user actually stopped on.
export function captureMapSettled(zoom: number, lat: number, lon: number): void {
  clearTimeout(mapSettledTimer);
  mapSettledTimer = setTimeout(() => {
    capture("map_settled", {
      zoom,
      lat: Number(lat.toFixed(4)),
      lon: Number(lon.toFixed(4)),
    });
  }, MAP_SETTLED_DEBOUNCE_MS);
}
