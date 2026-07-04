# Frontend localization (i18n) — design

**Date:** 2026-07-04
**Status:** Awaiting review

## Goal

Extract every user-facing string out of the frontend (`web/index.html`,
`web/app.js`) into a single localization catalog, and translate the current
English UI to Catalan. Only Catalan ships now, but the mechanism must make
adding a second language later a matter of adding one more object — no code
changes at call sites.

## Non-goals

- No language switcher / picker UI. `LANG` is a single constant (`"ca"`).
- Backend-provided strings stay where they are. Restriction layer **labels**
  and **tooltips** already arrive from the server in Catalan
  (`repositories/restrictions.py`); they are not touched here.
- No build step, bundler, or framework. The frontend stays vanilla JS loaded
  over plain `<script>` tags.
- Brand name **"RemoteScout"** is not translated (page `<title>` and the panel
  `<h1>`).

## Approach

A **plain JS module** `web/i18n.js`, loaded via a `<script>` tag **before**
`app.js`, exposing two globals:

```js
const STRINGS = { ca: { key: "…", … } };
let LANG = "ca";
function t(key, params) { … }   // looks up STRINGS[LANG][key], interpolates {name} params
```

Chosen over JSON-fetched locales because it needs no async load, no fetch
round-trip, and no ordering coordination — it matches the existing no-build
setup exactly. `t()` returns the template with `{placeholder}` tokens replaced
from `params`; a missing key returns the key itself (visible, debuggable).

### Static HTML strings

Marked in `index.html` with `data-i18n` attributes; a small
`applyStaticI18n()` in `i18n.js` walks `[data-i18n]` on load and sets each
element's `textContent`. Runs immediately (script is synchronous, DOM elements
above it are parsed). `<html lang="en">` becomes `<html lang="ca">`.

Labels that wrap an `<input>`/`<span>` (the sliders, the checkbox) can't have
their whole `textContent` replaced without destroying the child controls. For
those, wrap the translatable text in its own `<span data-i18n="…">` so only that
span's text is swapped.

### Dynamic JS strings

Every literal in `app.js` becomes a `t("key", {…})` call. Interpolated values
(counts, metres, degrees, error detail) are passed as params.

The `fetchFC(url, statusEl, noun)` helper currently takes an English `noun`
("zones", "anchors", "hotspots", "protected areas") and builds
`` `zoom in to see ${noun}` `` and `` `error: ${body.detail || res.status}` ``.
Change: callers pass a **string key** instead of an English word, and `fetchFC`
builds `t("zoomInToSee", { noun: t(nounKey) })` and `t("error", { detail })`.
This keeps the noun list translatable.

## String catalog (English → Catalan)

Keys are grouped by area. Catalan translations below; `{…}` are interpolation
params.

### Static (index.html)

| key | English | Catalan |
|-----|---------|---------|
| `region` | Region | Regió |
| `maxLength` | Max length | Longitud màxima |
| `minExposure` | Min exposure | Exposició mínima |
| `showAnchors` | Show anchors | Mostra els ancoratges |
| `restrictions` | Restrictions | Restriccions |
| `caveat` | Zones to scout — not confirmed-riggable. No bolts, trees, loose rock, access or permissions are verified. | Zones per explorar — no s'ha confirmat que es puguin equipar. No s'han verificat ancoratges, arbres, roca solta, accessos ni permisos. |

(The `m` unit suffix after the sliders stays as a literal `m` — not translated.)

### Dynamic (app.js)

| key | English template | Catalan template |
|-----|------------------|------------------|
| `searching` | searching… | cercant… |
| `loadingHotspots` | loading hotspots… | carregant punts d'interès… |
| `zonesCount` | {n} zones | {n} zones |
| `hotspotCells` | {n} hotspot cells (zoom in for zones) | {n} cel·les de punts d'interès (amplia per veure zones) |
| `anchorsCount` | {n} anchors | {n} ancoratges |
| `protectedAreasCount` | {n} protected areas | {n} espais protegits |
| `zoomInToSee` | zoom in to see {noun} | amplia per veure {noun} |
| `error` | error: {detail} | error: {detail} |
| `anchorError` | anchor error: {detail} | error d'ancoratges: {detail} |

Nouns (used inside `zoomInToSee`, passed by key):

| key | English | Catalan |
|-----|---------|---------|
| `nounZones` | zones | zones |
| `nounHotspots` | hotspots | punts d'interès |
| `nounAnchors` | anchors | ancoratges |
| `nounProtectedAreas` | protected areas | espais protegits |

Zone popup:

| key | English template | Catalan template |
|-----|------------------|------------------|
| `zonePopup` | height {min}–{max} m<br>length {lmin}–{lmax} m<br>{na} anchors · {np} lines | alçada {min}–{max} m<br>longitud {lmin}–{lmax} m<br>{na} ancoratges · {np} línies |

Density tooltip:

| key | English template | Catalan template |
|-----|------------------|------------------|
| `densityTooltip` | {n} candidate lines · up to {max} m{lenHint} | {n} línies candidates · fins a {max} m{lenHint} |
| `densityLenHint` | ` · {min}–{max} m long` | ` · {min}–{max} m de llarg` |

Density legend:

| key | English | Catalan |
|-----|---------|---------|
| `lineDensity` | Line density | Densitat de línies |
| `sparse` | sparse | escàs |
| `dense` | dense | dens |

Anchor popup:

| key | English template | Catalan template |
|-----|------------------|------------------|
| `anchorPopup` | anchor • elev {elev} m<br>{sectors} | ancoratge • elev {elev} m<br>{sectors} |
| `anchorSector` | drop {a}–{b}° ({drop} m) | caiguda {a}–{b}° ({drop} m) |

## Files touched

- **new** `web/i18n.js` — `STRINGS.ca`, `LANG`, `t()`, `applyStaticI18n()`.
- `web/index.html` — add `<script src="i18n.js">` before `app.js`; add
  `data-i18n` attributes; `lang="ca"`; call `applyStaticI18n()`.
- `web/app.js` — replace every user-facing literal with a `t()` call; change
  `fetchFC` to take a noun **key**.

No backend, no CSS changes.

## Testing

The frontend has no existing test suite (all tests are Python/pytest against the
backend). Verification is manual: run `just dev`, load the map, and confirm the
panel, status line, popups, tooltips, and density legend all render in Catalan,
with counts/units still interpolating correctly. A follow-up automated check is
out of scope unless requested.

## Risks / notes

- `t()` must not interpret templates as HTML by itself — but several strings
  (popups, tooltips) are *already* passed to Leaflet's `bindPopup`/`bindTooltip`
  as HTML in the current code, so behavior is unchanged. Anchor sector text is
  built from server-side numbers, same as today. No new XSS surface.
- Catalan copy above is a first pass; treat the table as reviewable — wording
  can be adjusted before or during implementation.
