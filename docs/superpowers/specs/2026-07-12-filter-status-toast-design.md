# Filter Status Toast Design

## Goal

Keep result counts and loading status out of the filter controls on desktop and mobile. Surface failures temporarily over the map so errors remain visible without occupying filter-card space.

## Behavior

- The desktop filters panel renders the filter controls and restriction controls, but no map, anchor, or restriction status lines.
- The mobile controls sheet follows the same rule.
- Successful zone and anchor counts are not shown elsewhere as part of this change.
- Map, anchor, and restriction errors appear in a shared temporary toast layered over the map.
- A newer error replaces the currently displayed error. The toast dismisses automatically after a short fixed interval and uses alert semantics for assistive technology.
- Loading and successful-result messages continue to drive no visible status UI.

## Components and Data Flow

`MapView` may continue reporting its existing status callbacks because it owns the request lifecycle. `App` separates error detail from informational status and supplies only error text to a small map-level toast component. Restriction metadata failures use the same error path.

`MapChrome` no longer passes a `statuses` node into `FiltersPanel` or `MobileControlSheet`. Removing that prop from the component boundaries prevents counts from accidentally returning to only one responsive layout.

## Error Handling

The existing localized error formatter remains the source of user-facing error text. Empty error state renders no toast. Replacing or clearing an error resets/cancels the dismissal timer so stale timers cannot hide a newer error.

## Testing

- Component tests verify neither desktop nor mobile filter containers accept or render status content.
- Application-level tests verify a reported successful zone count is absent.
- Application-level tests verify a reported error appears in the temporary toast and auto-dismisses using fake timers.
- The frontend test suite and TypeScript/build checks verify the prop cleanup across all call sites.
