import type posthog from "posthog-js";
import { loadPosthog } from "./analytics-loader";

// Write-only ingestion key: it can send events but cannot read data, so it is
// safe in client source. (Personal keys, phx_..., are secret and unused here.)
const POSTHOG_KEY = "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst";
const POSTHOG_HOST = "https://eu.i.posthog.com";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]);

export const MAP_SETTLED_DEBOUNCE_MS = 2000;

type AnalyticsEvent = [event: string, properties?: Record<string, unknown>];
type PosthogClient = typeof posthog;

let client: PosthogClient | undefined;
let loading: Promise<void> | undefined;
let queuedEvents: AnalyticsEvent[] = [];
let mapSettledTimer: ReturnType<typeof setTimeout> | undefined;

// The dev-build check is the real gate; the hostname check additionally keeps a
// local `npm run build` + `vite preview` silent.
export function shouldEnableAnalytics(isProd: boolean, hostname: string): boolean {
  return isProd && !LOCAL_HOSTS.has(hostname);
}

export function initAnalytics(
  isProd: boolean = import.meta.env.PROD,
  hostname: string = window.location.hostname,
): Promise<void> {
  if (!shouldEnableAnalytics(isProd, hostname)) return Promise.resolve();
  loading ??= loadAnalytics().catch(() => {
    queuedEvents = [];
    loading = undefined;
  });
  return loading;
}

async function loadAnalytics(): Promise<void> {
  const posthog = await loadPosthog();
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
  // `cookieless_mode: "always"` buys back *same-day* unique-visitor counts
  // without writing anything to the device: instead of a client-held
  // distinct_id, every event carries a `$posthog_cookieless` sentinel, and the
  // PostHog server hashes IP + User-Agent + a daily-rotating salt into a
  // visitor ID that stays stable across that visitor's events for the day and
  // changes the next day. It is layered on top of `persistence: "memory"`,
  // not a replacement for it: `cookieless_mode` disables PostHog's own
  // persistence I/O (loads/saves/removes all become no-ops), but
  // `persistence: "memory"` independently controls which storage backend gets
  // *constructed* in the first place — including in the brief window during
  // init before that disable takes effect, and for the explicit
  // remove()/cookie-expiry calls disabling triggers. Keeping `persistence:
  // "memory"` set means that construction and those calls only ever touch a
  // plain in-process object, never a real cookie or localStorage key,
  // regardless of what `cookieless_mode` does or how it evolves. What is still
  // lost: cross-DAY identity — retention and cohort analysis spanning days
  // remain meaningless, since a visitor's hashed ID changes every day.
  //
  // The four `disable_*` flags below are all pinned off in code because each
  // is independently toggleable from the PostHog dashboard and, if enabled,
  // writes to the device (session recording: DOM content; the other three:
  // raw localStorage keys) with no code change and no failing test.
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
  for (const [event, properties] of queuedEvents) {
    posthog.capture(event, properties);
  }
  queuedEvents = [];
}

export function capture(event: string, properties?: Record<string, unknown>): void {
  if (client) {
    client.capture(event, properties);
  } else if (loading) {
    queuedEvents.push([event, properties]);
  }
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
