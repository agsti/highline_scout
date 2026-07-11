# Mobile collapsed filter card: show meaningful state

## Problem

On mobile, the collapsed card at the bottom of the screen is the only persistent
UI. Today it shows an app title and a single truncated line:

```
Highline Scout
Length 20–150 m - Min exposure 30 m     [ Filters ]
```

Two things are wrong with it:

- The summary is `truncate`d and competes with the `Filters` button for width.
  The labels (`Length`, `Min exposure`) eat most of the row, so on a narrow
  phone the numbers — the only part that carries information — are the first
  thing to clip.
- Restriction overlays are drawn on the map in colour, but the legend that
  decodes those colours lives inside the sheet. With the sheet closed, a user
  sees coloured polygons with no way to tell ZEPA from ZEC from ENP.

## Goal

With the sheet closed, the card answers two questions: **what filters are
applied**, and **which restriction overlay is which colour**.

## Design

### Card structure

Drop the `Highline Scout` title row: on mobile the user knows which app they are
in, and the row costs a line of map. The card becomes:

- **Row 1** — the applied-filter summary, with the `Filters` button on the right.
- **Row 2** — the restriction legend, rendered only when at least one layer is
  enabled.

Default state (no layers enabled) is a single row — no taller than today. Rows
grow only when the user opts into overlays.

### Filter summary

Drop the labels, keep the numbers:

```
20–150 m · exp ≥30 m
```

It reflects the **applied** filters, not the drafts. Dragging a slider without
pressing Apply must not change it, so the card stays an honest description of
what is currently on the map.

This needs one new i18n key so translators own the abbreviation rather than
having the UI concatenate fragments:

```
ca: filterSummary: "{min}–{max} m · exp ≥{exp} m"
es: filterSummary: "{min}–{max} m · exp ≥{exp} m"
en: filterSummary: "{min}–{max} m · exp ≥{exp} m"
```

The three happen to coincide — `exp` abbreviates *exposició* / *exposición* /
*exposure* alike — but each language owns its own entry, so any of them can be
reworded without touching the others. `i18n.test.tsx` enforces key parity, so a
missing language fails the suite.

`Show anchors` is deliberately excluded. It is a display toggle, not a search
filter, and it is on by default; surfacing it would spend bar width on a
near-constant value.

### Restriction legend

A new `RestrictionLegend` component:

```tsx
interface RestrictionLegendProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
}
```

- Returns `null` when nothing is enabled, so Row 2 disappears entirely.
- Iterates `layers` and filters by `enabled` — **not** the other way round. This
  gives a stable legend order that does not reshuffle based on the order the
  user ticked the boxes, and silently ignores an enabled id with no metadata.
- Reuses `layer.color` from the API and `restrictionText(layer.id, lang, layer).label`
  for the name, so the swatch cannot drift from the map's fill and no new
  restriction strings are needed.
- Full labels, wrapping (`flex-wrap`). `Espais Naturals Protegits` is long; it
  wraps rather than truncating, since an unreadable label defeats the purpose.
- The swatch is `aria-hidden`; the text label carries the meaning for screen
  readers.

`App` passes it into `MobileControlSheet` as a `legend` ReactNode prop, matching
the existing `filters` / `statuses` / `restrictions` prop pattern on that
component. The sheet stays presentational.

### Out of scope

The desktop sidebar and the contents of the sheet itself are unchanged. The
existing `RestrictionLayerControls` inside the sheet keeps its full labels,
checkboxes and tooltips.

## Testing

- **`RestrictionLegend.test.tsx`** — renders nothing when none are enabled; one
  entry per enabled layer with the correct colour and localized label; order
  follows `layers` rather than `enabled`; an enabled id with no metadata is
  ignored.
- **`App.mobile.test.tsx`** — the collapsed card shows applied, not draft,
  values: move a slider and assert the card is unchanged, press Apply and assert
  it updates. Enable a restriction layer in the sheet and assert the legend
  appears on the collapsed card.
- **`i18n.test.tsx`** — existing catalog-parity test covers the new
  `filterSummary` key with no new test needed.
