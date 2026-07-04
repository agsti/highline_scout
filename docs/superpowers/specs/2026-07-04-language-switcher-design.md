# Language switcher — design

**Date:** 2026-07-04
**Status:** Awaiting review
**Builds on:** `2026-07-04-frontend-localization-design.md` (the `i18n.js` catalog +
`t()` helper already in place).

## Goal

Let the user pick the UI language from a control in the panel. Add **Spanish**
and re-add **English** alongside the existing **Catalan**, so the switcher has
something to switch between. Remember the choice across visits and auto-detect a
sensible default on first visit.

## Non-goals

- No backend changes. Restriction layer **labels/tooltips** come from the server
  in Catalan and stay Catalan in every UI language (they are mostly proper names
  — PEIN, Parcs Naturals, Reserves de Fauna). Noted as a known limitation.
- No French (yet). The catalog structure makes it a one-object addition later.
- No full page reload on switch — the map view (center/zoom, accumulated zones)
  is preserved.
- "RemoteScout" brand stays untranslated.

## Languages

Three catalogs under `STRINGS`: `ca` (exists), `es` (new), `en` (re-added
verbatim from the pre-localization strings). Every key present in `ca` exists in
all three — a startup assertion guards this in dev.

## Switcher UI

A `<select id="lang">` at the top of the panel (above Region), with a translated
`data-i18n="language"` label ("Idioma" / "Idioma" / "Language"). Options name
each language **in its own tongue**, never translated:

```html
<label><span data-i18n="language">Language</span>
  <select id="lang">
    <option value="ca">Català</option>
    <option value="es">Español</option>
    <option value="en">English</option>
  </select></label>
```

## Initial language & persistence

Resolved in `i18n.js` **before** `applyStaticI18n()` runs, by a new
`pickInitialLang()`:

1. `localStorage.getItem("lang")` — if it names an available catalog, use it.
2. Else walk `navigator.languages` (then `navigator.language`); first entry
   whose 2-letter prefix matches an available catalog wins.
3. Else fall back to `"ca"`.

`localStorage` access is wrapped in try/catch (private-mode / disabled storage
must not break the page — fall through to detection/default).

`LANG` is initialised from `pickInitialLang()` instead of the hardcoded `"ca"`.
`document.documentElement.lang` is set to `LANG` on load and on every switch.

## Switching at runtime

On `#lang` change (wired in `app.js`):

1. `setLang(value)` in `i18n.js`: set `LANG`, write `localStorage["lang"]`
   (try/catch), set `document.documentElement.lang`.
2. `applyStaticI18n()` — re-fills all `[data-i18n]` static labels.
3. Re-render dynamic content by re-running the existing refresh functions:
   `refresh()`, `refreshAnchors()`, `refreshRestrictions()`. These rebuild the
   status line, zone/anchor popups, density tooltips, and the density legend
   (whose `onAdd` reads `t()` at add-time) in the new language.

Any popup already **open** at switch time keeps its old-language text until
reopened — acceptable; re-rendering the layers refreshes the bound content for
the next open. `#lang.value` is set to `LANG` on load so the control reflects the
resolved language.

## New/added catalog keys

- `language`: `ca` "Idioma", `es` "Idioma", `en` "Language".
- Full `es` catalog: every existing key translated to Castilian (e.g.
  `searching` "buscando…", `zonesCount` "{n} zonas", `anchorSector`
  "caída {a}–{b}° ({drop} m)", caveat translated).
- Full `en` catalog: the verbatim pre-localization English strings (recovered
  from the previous spec / git history), e.g. `zonesCount` "{n} zones",
  `caveat` "Zones to scout — not confirmed-riggable. …".

## Files touched

- `web/i18n.js` — add `es` and `en` catalogs + `language` key to `ca`; add
  `pickInitialLang()`, `setLang()`; init `LANG` from `pickInitialLang()`; set
  `documentElement.lang`; dev-only key-parity assertion.
- `web/index.html` — add the `#lang` select + label above Region.
- `web/app.js` — wire `#lang` change → `setLang()` + re-render; set
  `#lang.value = LANG` on load.
- No CSS required (reuses existing `#panel label` styling); a minor tweak only
  if the select needs spacing.

## Testing

- **Automated (node):** extend the existing catalog check to assert all three
  languages define exactly the same key set (no missing/extra keys), and that
  `t()` interpolation works under each `LANG`.
- **Manual (browser, `just dev`):** load the app, switch ca→es→en via the
  select, confirm panel labels, status line, density legend, and a zone/anchor
  popup all change language; reload and confirm the choice persisted; clear
  `localStorage` and confirm browser-language auto-detect picks a sane default.

## Risks / notes

- Restriction labels/tooltips stay Catalan in all languages (backend-sourced).
  Documented; out of scope.
- `navigator.language` prefix matching is coarse (e.g. `en-GB` → `en`) — fine
  for a 3-language set.
- `es`/`en` copy is a first pass and reviewable; `en` should match the original
  wording exactly.
