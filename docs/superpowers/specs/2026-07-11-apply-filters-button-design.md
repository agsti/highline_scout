# Apply Filters Button — Design

## Problem

The filter controls are live: `App` pushes every slider change straight into
`MapView`, whose zone-fetch effect depends on `[minLen, maxLen, minExposure]`.
Dragging a slider therefore fires a `/zones` request per drag frame and clears
the zone layer per frame. The user wants an explicit "Apply filters" button so a
search runs only when asked for.

## Behaviour

The two query filters (line length range, minimum exposure) become a **draft**
that the sliders edit. The map keeps showing results for the last **applied**
values until the user presses Apply.

- Moving a slider updates only its own value label. No request.
- Apply copies draft → applied, which is what triggers a new search.
- Apply is disabled while the draft equals the applied values.
- "Show anchors" is **not** part of the draft. It stays live, toggling the
  anchor layer immediately. It is a display toggle, not a search parameter.
- Panning the map still re-searches, using the applied values. Unchanged.
- First paint: draft and applied both start at the defaults (`[20, 150]`, `30`),
  so the initial search happens exactly as it does today.

## State (`App.tsx`)

| State | Read by | Written by |
| --- | --- | --- |
| `draftLengthRange`, `draftMinExposure` | the sliders and their labels | slider `onValueChange` |
| `appliedLengthRange`, `appliedMinExposure` | `MapView` (the query) | `handleApply` only |
| `showAnchors` | `MapView` | the checkbox, immediately |

`canApply` is `draft !== applied` compared over the three numbers.
`handleApply` copies draft into applied, captures analytics, and closes the
mobile sheet.

`MapView` needs no internal change: it receives the applied values, so both its
fetch effect and its zone-layer-clearing effect stop firing mid-drag on their own.

The mobile trigger's `summary` line switches to the **applied** values, because
it describes what is currently on the map.

## Components

**`FilterControls`** becomes a `<form onSubmit={apply}>` with the button as its
`type="submit"`, giving Enter-to-apply and the right semantics for a filter
form. The button renders at the bottom of the form, so it appears under the
filters and above the statuses and restrictions in both the desktop sidebar and
the mobile sheet, without touching either layout component.

Props go from five callbacks to four: `onLengthRangeCommit` and
`onMinExposureCommit` are dropped; `onApply` and `canApply` are added.

**`MobileControlSheet`**: its `Sheet` becomes controlled, taking `open` and
`onOpenChange` from `App`, so `handleApply` can close it — otherwise the sheet
would cover the map the user just searched. Its `actions?: ReactNode` prop is
deleted: it is unused today and the button lands inside `filters` instead.

**`DesktopSidebar`**: unchanged.

**i18n**: one new key, `applyFilters`, in all three locales (ca, es, en).

## Analytics

The `onValueCommit` callbacks exist only to stop `filter_changed` firing once
per drag frame. With a deferred search, "the user released the slider" is no
longer the meaningful event and "the user ran a search" is. So `filter_changed`
is **replaced** by a single `filters_applied` capture on Apply, carrying
`{ min_len, max_len, min_exposure }`. The commit plumbing is deleted.

## Testing

Vitest + React Testing Library, following the existing test files.

- `FilterControls`: the button is disabled when clean and enabled when dirty;
  clicking it calls `onApply`; moving a slider does not.
- `App` integration: dragging a length slider does not change the `fetchZones`
  arguments until Apply is pressed. This is the core guarantee of the feature.
- Analytics: Apply captures `filters_applied` with the applied values.
- Mobile: pressing Apply closes the sheet.

## Out of scope

Keeping a `filter_changed` event for abandoned drafts. Deferring "Show anchors".
Any change to how panning triggers a search.
