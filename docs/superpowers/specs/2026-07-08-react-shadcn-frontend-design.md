# React + shadcn Frontend Redesign

Date: 2026-07-08

## Goal

Rebuild the Highline Scout frontend as a React application using shadcn-style
components while preserving every current user-facing feature. The redesign is a
frontend migration with one deliberate UX improvement: desktop remains a left
sidebar map tool, while mobile uses a compact bottom peek card that expands into
a bottom sheet.

The new UI should feel like a light topographic field tool: map-first, compact,
clear, and terrain-oriented. Results remain zones to scout, never confirmed
riggable lines.

## Non-Goals

- Do not change backend API semantics for zones, density, anchors,
  restrictions, or regions.
- Do not add new product concepts such as saved scouting sessions, zone
  selection workflows, user accounts, or editable notes.
- Do not change the offline precompute pipeline.
- Do not remove Catalan, Spanish, or English support.

## Chosen Approach

Use a full React parity rewrite with targeted UX upgrades.

Create a new `frontend/` Vite + React + TypeScript app. Use Tailwind and
shadcn component source for controls, dialogs, sheets, sliders, switches,
checkboxes, selects, and compact UI primitives. FastAPI remains the API server
and production static host. During development, Vite runs separately and proxies
API requests to FastAPI.

This approach avoids mixing old imperative DOM code with React, gives shadcn the
build system it expects, and keeps scope bounded to feature parity plus the
mobile bottom-sheet improvement.

## Alternatives Considered

### Incremental React Islands

Keep `web/` and mount React into pieces of the current page.

This lowers short-term migration risk, but shadcn, Tailwind, Leaflet state, and
old DOM event handlers would coexist awkwardly. It would also leave the project
with two frontend patterns to maintain.

### Larger Product Redesign

Use the React migration to add new concepts such as selectable zones, a detail
rail, saved sessions, or richer stats.

This could be useful later, but it expands the migration before parity is
verified. It is intentionally out of scope for this redesign.

## Architecture

The repository gains a `frontend/` directory:

- `frontend/src/` contains the React app.
- `frontend/src/components/` contains reusable UI and map components.
- `frontend/src/lib/` contains typed API clients, i18n helpers, map utilities,
  and feature-processing helpers.
- `frontend/src/styles/` or the app stylesheet contains Tailwind and shadcn
  theme tokens.
- `frontend/dist/` is the production build output and is not committed.

FastAPI serves the React production build when it exists. The old `web/`
directory may remain as a temporary fallback during migration, but the target
production path is the React build. Docker becomes a multi-stage build: a Node
stage builds the frontend, and the Python runtime stage copies the built assets.

Local development uses two processes:

- FastAPI on port `8000` for API endpoints.
- Vite on its own port for frontend hot reload, proxying `/regions`, `/zones`,
  `/density`, `/anchors`, and `/restrictions` to FastAPI.

`justfile` will grow commands for frontend install/build/dev. It will also add
a documented development workflow for running FastAPI and Vite together.

## UI Design

The app remains a map-first tool.

### Desktop

Desktop keeps the current left sidebar pattern:

- Sidebar contains region, max length, minimum exposure, anchors toggle,
  restriction controls, safety caveat, status lines, and language controls.
- Sidebar can collapse.
- The map fills the remaining viewport.
- Collapsing or expanding the sidebar invalidates the Leaflet map size after
  layout transition.

### Mobile

Mobile changes from a left drawer to a bottom control surface:

- The map fills the screen.
- A compact floating peek card sits at the bottom.
- The peek card shows the most important state: region, active filters, current
  status, and an affordance to expand.
- Expanding opens a bottom sheet containing the full control set.
- The sheet is dismissible without resetting map state.
- Map padding and Leaflet size invalidation keep controls from obscuring core
  map interactions.

### Visual Direction

Use a light topographic field-tool style:

- Off-white surfaces for controls.
- Muted terrain-adjacent neutrals for borders and secondary backgrounds.
- Deep teal for zones, anchors, primary controls, and data emphasis.
- Compact labels and restrained spacing.
- No decorative blobs, generic gradients, or ornamental panels.

The map remains the main visual subject. UI surfaces support inspection and
control rather than acting as a marketing page.

## Components

The React app centers on a `MapView` component that owns the Leaflet instance
and imperative layers. React owns app state, controls, language, loading, and
dialogs.

Primary components:

- `AppShell`: responsive layout wrapper.
- `DesktopSidebar`: desktop controls and collapse behavior.
- `MobileControlSheet`: bottom peek card and expanded bottom sheet.
- `MapView`: Leaflet initialization, OSM base layer, layers, context menu, and
  map event wiring.
- `SafetyDisclaimerDialog`: shown on each load, not persisted.
- `LanguageSwitcher`: reused in sidebar/sheet and disclaimer dialog.
- `RestrictionLayerControls`: layer checkboxes, swatches, descriptions, and
  highlighted warning text.
- `DensityLegend`: rendered when density mode is active.
- `StatusLine`: small status messages for zones/density, anchors, and
  restrictions.
- Filter components for region select, max length slider, minimum exposure
  slider, and anchor visibility.

Use shadcn components for common controls and overlay patterns. Leaflet popups,
tooltips, and map layers remain Leaflet-owned.

## Data Flow And Behavior

The React app must preserve current behavior.

### Regions

- Load regions from `GET /regions`.
- Selecting a region clears accumulated zones and fits the map to the region's
  bounds.
- If the URL contains valid `lat`, `lng`, and `z` parameters, initialize the map
  there instead of flying to the first region.

### Density And Zones

- At Leaflet zoom `<= 12`, clear zones and request density cells from
  `GET /density`.
- Above zoom `12`, request zones from `GET /zones`.
- Zone requests include region, viewport bbox, max length, and minimum exposure.
- Zones accumulate across pans and zooms in zone mode.
- Duplicate zones are skipped using the current snapped-centroid key behavior.
- Changing max length or minimum exposure clears accumulated zones and refetches.
- Density cells are rank-styled against the cells currently in view.
- The density legend appears only while density mode is active.

### Anchors

- Anchors are optional and controlled by the anchors toggle.
- Do not request anchors below the current minimum zoom threshold.
- When anchor count is under the current detail threshold, render sector wedges
  plus center markers.
- When anchor count is higher, render lightweight dots.
- Anchor popups include elevation and drop sectors.

### Restrictions

- Load restriction metadata from `GET /restrictions/layers`.
- Enabled layers request viewport features from `GET /restrictions`.
- Restrictions are independent of selected region.
- Preserve layer colors, popups, checkbox behavior, and highlighted description
  clauses.
- Catalan restriction text comes from the backend. Spanish and English frontend
  translations override backend text when available.

### Map Context Menu And Share Links

- Preserve right-click map menu on desktop.
- Provide the same actions on touch devices through a visible share/actions
  control in the mobile peek card or bottom sheet.
- Keep "View in Google Maps".
- Keep "Copy link" with `lat`, `lng`, and `z` query parameters.
- Clipboard failure falls back to a prompt-style copy path or a clear visible
  URL.

### Safety Disclaimer

- Show the disclaimer on every page load.
- Do not persist acceptance.
- Allow language switching before acceptance.
- Keep it keyboard accessible.

## i18n

Move localization out of globals and into TypeScript modules:

- `strings.ts` for UI catalogs.
- `restrictionStrings.ts` for Spanish and English restriction translations.
- `I18nProvider` for active language state.
- `useT()` for string lookup and interpolation.

Catalan remains the base/source-of-truth catalog. Spanish and English must keep
the same key set as Catalan. Missing keys are surfaced in development rather
than silently blank.

Some strings feed Leaflet popups/tooltips and contain HTML. Keep these strings
audited and constrained to known app-authored markup.

## Error Handling

- Treat `413` responses as viewport-cap messages telling the user to zoom in.
- Show endpoint errors with backend `detail` when available.
- Ignore or abort stale fetches when map moves or filters change quickly, so old
  responses do not overwrite newer state.
- If density data is unavailable for a region, show a clear status and keep the
  map usable.
- If restriction metadata or features fail to load, leave the map usable and
  report the error in the restrictions status area.
- Empty feature collections produce counts, not errors.

## Testing And Verification

Frontend tests cover:

- i18n catalog parity and interpolation.
- Restriction translation fallback behavior.
- URL initial view parsing.
- Zone dedupe key behavior.
- Density rank calculation.
- Filter-state behavior around resetting accumulated zones.
- Language switching for static controls and map popup/tooltip content.

Verification commands include:

- Frontend build.
- Frontend tests.
- Existing backend test suite via `just test`.
- A manual or automated browser check that desktop sidebar, mobile bottom sheet,
  density mode, zone mode, anchors, restrictions, language switching, and the
  disclaimer all work.

## Migration Plan Outline

1. Add Vite + React + TypeScript + Tailwind + shadcn tooling under `frontend/`.
2. Add typed API clients and shared helper utilities.
3. Port i18n catalogs and restriction translations.
4. Build the responsive shell: desktop sidebar and mobile peek card/sheet.
5. Build `MapView` with base map, initial URL view, map events, and resize
   invalidation.
6. Port density and zone rendering with current thresholds, styling, and
   dedupe behavior.
7. Port anchors with wedge/dot rendering.
8. Port restrictions with metadata loading, translated text, layer toggles, and
   map overlays.
9. Port map context menu, share links, status lines, and safety disclaimer.
10. Wire FastAPI static serving, Docker, and `justfile` commands.
11. Verify feature parity and then remove or archive the old static `web/`
    frontend.

## Acceptance Criteria

- The production app is served from the React build.
- All current frontend functionality is present in the React app.
- Desktop uses a collapsible left sidebar.
- Mobile uses a bottom peek card that expands into a bottom sheet.
- Catalan, Spanish, and English UI switching works.
- Protected-area translations preserve the Catalan backend fallback.
- Existing API endpoints continue to work without semantic changes.
- Frontend build succeeds.
- Backend tests pass.
