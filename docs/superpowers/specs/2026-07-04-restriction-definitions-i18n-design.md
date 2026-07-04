# Translate restriction definitions — design

**Date:** 2026-07-04
**Status:** Awaiting review
**Builds on:** `2026-07-04-language-switcher-design.md`.

## Goal

Translate the protected-area restriction **definitions** — each layer's `label`,
`tooltip`, and highlighted `highlight` clause — so they follow the selected UI
language (ca/es/en) instead of always showing Catalan. Closes the known
limitation noted in the language-switcher spec.

## Scope

Three layers: `pein`, `parcs`, `fauna`. Their text is defined in the backend
`LAYERS` registry (`highliner/repositories/restrictions.py`) and served over
`GET /restrictions/layers`. The frontend renders them as the panel checkbox
labels, the inline descriptions (with a `<mark>`-highlighted clause via
`appendDescText`), and the map feature popups.

## Non-goals

- No backend change. The server keeps sending the Catalan `label`/`tooltip`/
  `highlight`; the frontend uses those verbatim for `ca` (so Catalan is never
  duplicated) and overrides them for `es`/`en`.
- Layer **colors** and per-feature area **names** (from the WFS data) are not
  translated.
- The `pein` label stays "PEIN" in every language (proper acronym).

## Approach

Client-side, in `web/i18n.js`, matching the existing i18n system:

- New `RESTRICTION_STRINGS = { es: {...}, en: {...} }`, keyed by layer id, each
  entry `{ label, tooltip, highlight }`. No `ca` entry — Catalan falls back to
  the server text.
- New resolver `restrictionText(id, fallback)`: returns the active language's
  entry for `id`, else `fallback` (the server-provided `{label,tooltip,
  highlight}`), else `{}`.

Per language, `highlight` MUST remain a verbatim substring of that language's
`tooltip`, since `appendDescText` locates it with `indexOf`.

## Frontend wiring (`web/app.js`)

- Add a `restrictionServer` map; in `loadRestrictionLayers()` store the server's
  `{label,tooltip,highlight}` per id there (the Catalan fallback), then build
  each row's label and description from `restrictionText(id, server)`.
- Give each row `dataset.layer = id` and wrap the label text in a
  `<span class="restr-label">` (set via `textContent`, not `innerHTML`) so it
  can be re-translated in place.
- `restrictionLabel[id]` (used by popups) is set to the resolved label.
- New `applyRestrictionI18n()`: for each row, re-resolve for the current
  language and update `restrictionLabel[id]`, the `.restr-label` text, and the
  description (clear + re-run `appendDescText`) — preserving the checkbox and
  its shown/hidden description state.
- The language-switch handler calls `applyRestrictionI18n()` before
  `refreshRestrictions()` (so refreshed popups read the new label).

## Testing

- **Node:** assert each of `es`/`en` defines all three layers with non-empty
  `label`/`tooltip`/`highlight`, and that each `highlight` is a substring of its
  `tooltip` (the `<mark>` invariant).
- **Browser (`just dev`):** enable a restriction layer, switch ca→es→en, and
  confirm the checkbox label, the inline description, the highlighted clause, and
  a feature popup all change language; checkbox stays checked and its
  description stays visible across the switch.

## Risks / notes

- es/en copy is a faithful first pass and reviewable in `i18n.js`.
- If the backend adds a new layer, it shows in Catalan (server fallback) until
  an `es`/`en` entry is added — graceful degradation, same pattern as `t()`.
