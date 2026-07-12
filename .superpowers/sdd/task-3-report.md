# Task 3 report: anchor and restriction overlay extraction

## Delivered

- Added `useAnchorLayer`, which owns the anchor layer's Leaflet lifecycle and preserves its zoom gate, request, rendering, abort, status, and error behavior.
- Added `useRestrictionLayer`, which owns the restrictions GeoJSON lifecycle, current metadata lookup, request, 413 zoom guidance, status, and error behavior.
- Simplified `MapView` to compose the two hooks without changing its public props or callbacks.
- Added focused hook tests for disabled/empty selections, anchor zoom guidance, and restriction 413 handling.

## TDD evidence

`useAnchorLayer.test.tsx` was added before implementation and initially failed to resolve `./useAnchorLayer`, as expected. The restriction hook test was likewise authored before its hook implementation.

## Verification

- Focused: `node node_modules/vitest/vitest.mjs run src/components/map/useAnchorLayer.test.tsx src/components/map/useRestrictionLayer.test.tsx src/components/map/MapView.test.tsx` — 19 passed.
- Full frontend: `node node_modules/vitest/vitest.mjs run` — 28 files / 114 tests passed.
- Production build: `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build` — passed.
- `git diff --check` — passed.

The commands used `/home/gus/.nvm/versions/node/v20.20.2/bin/node` because `node` and `npm` are not on the shell PATH. Vitest continues to report the pre-existing `act(...)` warning from the mobile context-menu MapView test; Vite continues to report its existing bundle-size advisory.
