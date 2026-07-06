# Copy viewport link — design

## Context

The right-click map menu (added in b1dbb7e) currently shows a single popup
with one link, "View in Google Maps", built from the clicked point. This adds
a second item, "Copy link", that lets a scout share the exact spot (and zoom)
they're looking at via a URL that reopens the app at that same view.

## URL scheme

Query params `lat`, `lng`, `z`, e.g.:

```
https://.../?lat=41.5912&lng=1.8341&z=15
```

- `lat`/`lng` are the right-clicked point, rounded to 5 decimals (~1m
  precision).
- `z` is `map.getZoom()` at the moment of the click.
- Naming matches the existing `z` convention already used for other API
  query strings in `app.js`.

## Right-click popup becomes a 2-item menu

The `contextmenu` handler still opens one Leaflet popup at the clicked
`latlng`, but its content is built as a DOM node (instead of an HTML string)
so a click handler can be attached directly, with two entries:

1. **View in Google Maps** — existing `<a>`, unchanged.
2. **Copy link** — a `<button>` that:
   - builds the URL from the clicked lat/lng and current zoom,
   - calls `navigator.clipboard.writeText(url)`,
   - on success: closes the popup and briefly overwrites the `#status`
     element's text with a translated "Link copied" message, restoring
     whatever text was there before after ~2 seconds,
   - on failure (clipboard API rejected or unavailable): falls back to
     `prompt()` pre-filled with the URL so the user can copy it manually.

## Load behavior

Before the existing hardcoded `map.setView([41.6, 1.83], 13)`, parse
`new URLSearchParams(location.search)` for `lat`, `lng`, `z`. If all three
are present and parse to finite numbers, use them as the initial view
instead of the hardcoded default. Otherwise, behavior is unchanged.

## i18n

New keys added to `ca`/`es`/`en` in `i18n.js`, next to the existing
`viewInGoogleMaps` key:

- `copyLink` — menu item label.
- `linkCopied` — transient confirmation text shown in `#status`.

## Testing

Manual, since this is a small frontend-only change with no existing test
harness for map interactions:

- Right-click, click "Copy link", paste the result into a new tab — confirm
  the map opens centered at the same point and zoom.
- Repeat in all three languages (ca/es/en) and confirm both menu items and
  the confirmation text are translated.
- Force a clipboard rejection (e.g. via devtools permission override) and
  confirm the `prompt()` fallback shows the correct URL.
- Confirm loading the app with no query params still falls back to the
  default Montserrat view.
