# React shadcn Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current static `web/` frontend with a Vite React TypeScript app using shadcn-style components while preserving all current functionality and changing mobile controls to a bottom peek card/sheet.

**Architecture:** Add a new `frontend/` app that owns all UI, state, i18n, typed API calls, and Leaflet rendering. FastAPI keeps the same API endpoints and serves `frontend/dist` in production, falling back to `web/` during migration if the React build is absent.

**Tech Stack:** Vite, React, TypeScript, Tailwind CSS, shadcn component source, Leaflet, Vitest, Testing Library, FastAPI, uv, Docker multi-stage build, npm with Node `>=20`.

## Global Constraints

- Preserve backend API semantics for `/regions`, `/zones`, `/density`, `/anchors`, `/restrictions/layers`, and `/restrictions`.
- Preserve all current frontend features: regions, density/zones switching, accumulated zone dedupe, anchors, restrictions, share links, disclaimer, and `ca`/`es`/`en` language switching.
- Desktop uses a collapsible left sidebar.
- Mobile uses a compact bottom peek card that expands into a bottom sheet.
- Catalan remains the base/source-of-truth UI catalog.
- Catalan restriction labels/tooltips/highlights come from the backend; Spanish and English frontend translations override when available.
- Use internal map coordinates only through existing API bbox boundaries; the frontend sends `bbox_lonlat`.
- Results remain "zones to scout", never confirmed riggable lines.
- Keep old `web/` files untouched until React parity is verified.
- Do not commit `frontend/dist`, `frontend/node_modules`, or companion `.superpowers/` files.

---

## File Structure

Create:

- `frontend/package.json`: npm scripts and frontend dependencies.
- `frontend/package-lock.json`: locked npm dependency graph.
- `frontend/index.html`: Vite HTML entry.
- `frontend/vite.config.ts`: Vite config and API proxy.
- `frontend/tsconfig.json`, `frontend/tsconfig.node.json`: TypeScript config.
- `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`: frontend test config.
- `frontend/postcss.config.js`, `frontend/tailwind.config.ts`: Tailwind config.
- `frontend/components.json`: shadcn metadata.
- `frontend/src/main.tsx`: React entry.
- `frontend/src/App.tsx`: top-level app state and composition.
- `frontend/src/styles/globals.css`: Tailwind, shadcn tokens, app layout, Leaflet imports.
- `frontend/src/lib/api.ts`: typed fetch clients for existing backend endpoints.
- `frontend/src/lib/geo.ts`: URL view parsing, bbox serialization, destination points, anchor wedge points.
- `frontend/src/lib/map-style.ts`: zone/density colors, density rank, zone dedupe key.
- `frontend/src/lib/i18n/strings.ts`: UI catalogs copied from `web/i18n.js`.
- `frontend/src/lib/i18n/restrictionStrings.ts`: restriction translation catalogs copied from `web/i18n.js`.
- `frontend/src/lib/i18n/I18nProvider.tsx`: language state, `useT()`, interpolation, persistence.
- `frontend/src/lib/i18n/index.ts`: i18n exports.
- `frontend/src/components/ui/*.tsx`: shadcn component source used by the app.
- `frontend/src/components/AppShell.tsx`: responsive shell, desktop/sidebar/mobile placement.
- `frontend/src/components/DesktopSidebar.tsx`: desktop controls.
- `frontend/src/components/MobileControlSheet.tsx`: mobile peek card and bottom sheet.
- `frontend/src/components/FilterControls.tsx`: region, sliders, anchors toggle.
- `frontend/src/components/LanguageSwitcher.tsx`: flag/segmented language controls.
- `frontend/src/components/RestrictionLayerControls.tsx`: restriction toggles/descriptions.
- `frontend/src/components/SafetyDisclaimerDialog.tsx`: disclaimer modal.
- `frontend/src/components/StatusLine.tsx`: small status text component.
- `frontend/src/components/map/MapView.tsx`: Leaflet map and layer orchestration.
- `frontend/src/components/map/leafletLayers.ts`: imperative layer creation/update helpers.
- `frontend/src/components/map/popups.ts`: localized popup/tooltip HTML builders.
- `frontend/src/types/geojson.ts`: minimal GeoJSON types used by the frontend.
- `frontend/src/types/highliner.ts`: API/domain types.
- `frontend/src/lib/*.test.ts`, `frontend/src/lib/i18n/*.test.ts`: helper tests.

Modify:

- `.gitignore`: ignore `frontend/node_modules/` and `frontend/dist/`.
- `justfile`: add frontend install/dev/build/test commands and a documented two-process dev workflow.
- `highliner/app.py`: serve React build when present, fallback to `web/`.
- `Dockerfile`: build frontend in a Node stage and copy `frontend/dist`.
- `.github/workflows/ci.yml`: install Node, run frontend tests/build, keep backend checks.

---

### Task 1: Frontend Tooling Skeleton

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/components.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/globals.css`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: no frontend code exists yet.
- Produces: `npm test`, `npm run build`, and `npm run dev` work from `frontend/`.

- [ ] **Step 1: Create package metadata**

Create `frontend/package.json`:

```json
{
  "name": "highliner-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=20"
  },
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 127.0.0.1",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@radix-ui/react-checkbox": "^1.1.3",
    "@radix-ui/react-dialog": "^1.1.6",
    "@radix-ui/react-label": "^2.1.2",
    "@radix-ui/react-select": "^2.1.6",
    "@radix-ui/react-slider": "^1.2.3",
    "@radix-ui/react-slot": "^1.1.2",
    "@radix-ui/react-switch": "^1.1.3",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "leaflet": "^1.9.4",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "tailwind-merge": "^2.5.5",
    "tailwindcss-animate": "^1.0.7"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/leaflet": "^1.9.15",
    "@types/node": "^22.10.2",
    "@types/react": "^18.3.17",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.2",
    "vite": "^6.0.5",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 2: Install dependencies**

Run:

```bash
cd frontend
npm install
```

Expected: `frontend/package-lock.json` is created and npm exits successfully.

- [ ] **Step 3: Create Vite and TypeScript config**

Create `frontend/vite.config.ts`:

```ts
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/regions": "http://127.0.0.1:8000",
      "/zones": "http://127.0.0.1:8000",
      "/density": "http://127.0.0.1:8000",
      "/anchors": "http://127.0.0.1:8000",
      "/restrictions": "http://127.0.0.1:8000",
    },
  },
});
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "vitest.config.ts", "tailwind.config.ts"]
}
```

- [ ] **Step 4: Create Vitest config**

Create `frontend/vitest.config.ts`:

```ts
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 5: Create Tailwind and shadcn config**

Create `frontend/postcss.config.js`:

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

Create `frontend/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;

export default config;
```

Create `frontend/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 6: Create minimal app entry and styles**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="ca">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Highline Scout</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/globals.css";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Create `frontend/src/App.tsx`:

```tsx
export function App() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <h1 className="text-lg font-semibold">Highline Scout</h1>
    </main>
  );
}
```

Create `frontend/src/styles/globals.css`:

```css
@import "leaflet/dist/leaflet.css";

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 132 25% 98%;
    --foreground: 168 30% 13%;
    --card: 132 25% 98%;
    --card-foreground: 168 30% 13%;
    --popover: 132 25% 98%;
    --popover-foreground: 168 30% 13%;
    --primary: 176 70% 28%;
    --primary-foreground: 0 0% 100%;
    --secondary: 150 22% 92%;
    --secondary-foreground: 168 30% 13%;
    --muted: 150 18% 93%;
    --muted-foreground: 164 12% 42%;
    --accent: 166 35% 89%;
    --accent-foreground: 168 30% 13%;
    --destructive: 7 52% 42%;
    --destructive-foreground: 0 0% 100%;
    --border: 150 18% 82%;
    --input: 150 18% 82%;
    --ring: 176 70% 28%;
    --radius: 0.45rem;
  }

  * {
    @apply border-border;
  }

  html,
  body,
  #root {
    height: 100%;
  }

  body {
    @apply m-0 bg-background font-sans text-foreground antialiased;
  }
}
```

- [ ] **Step 7: Update gitignore**

Append to `.gitignore`:

```gitignore
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 8: Verify skeleton**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: both commands exit `0`; Vite creates `frontend/dist/`.

- [ ] **Step 9: Commit**

```bash
git add .gitignore frontend
git commit -m "feat: scaffold react frontend"
```

---

### Task 2: Shared UI Primitives And Helper Utilities

**Files:**
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/checkbox.tsx`
- Create: `frontend/src/components/ui/dialog.tsx`
- Create: `frontend/src/components/ui/label.tsx`
- Create: `frontend/src/components/ui/select.tsx`
- Create: `frontend/src/components/ui/slider.tsx`
- Create: `frontend/src/components/ui/switch.tsx`
- Create: `frontend/src/components/ui/sheet.tsx`
- Create: `frontend/src/components/ui/separator.tsx`
- Create: `frontend/src/lib/geo.ts`
- Create: `frontend/src/lib/map-style.ts`
- Create: `frontend/src/types/geojson.ts`
- Create: `frontend/src/types/highliner.ts`
- Create: `frontend/src/lib/geo.test.ts`
- Create: `frontend/src/lib/map-style.test.ts`

**Interfaces:**
- Consumes: React/Tailwind skeleton from Task 1.
- Produces:
  - `cn(...inputs: ClassValue[]): string`
  - `initialViewFromSearch(search: string): MapViewState | null`
  - `bboxLonLatParam(bounds: LatLngBoundsLike): string`
  - `destPoint(lat: number, lon: number, bearingDeg: number, distM: number): [number, number]`
  - `wedge(lat: number, lon: number, start: number, end: number, radiusM?: number): [number, number][]`
  - `tealShade(t: number): string`
  - `densityRank(n: number, sorted: number[]): number`
  - `zoneKey(feature: ZoneFeature): string`

- [ ] **Step 1: Add utility and UI primitive files**

Run shadcn or add source-equivalent files for:

```bash
cd frontend
npx shadcn@latest add button checkbox dialog label select slider switch sheet separator
```

If the CLI asks to overwrite config, answer no. If the CLI fails because package versions have moved, create the same components manually using the installed Radix packages and the `cn` helper below.

Create `frontend/src/lib/utils.ts`:

```ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Define frontend types**

Create `frontend/src/types/geojson.ts`:

```ts
export type Position = [number, number];

export interface PointGeometry {
  type: "Point";
  coordinates: Position;
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

export interface Feature<G, P> {
  type: "Feature";
  geometry: G;
  properties: P;
}

export interface FeatureCollection<F extends Feature<unknown, unknown>> {
  type: "FeatureCollection";
  features: F[];
}
```

Create `frontend/src/types/highliner.ts`:

```ts
import type { Feature, FeatureCollection, PointGeometry, PolygonGeometry } from "./geojson";

export interface Region {
  name: string;
  bounds_lonlat: [number, number, number, number];
}

export interface RegionsResponse {
  regions: Region[];
}

export interface ZoneProperties {
  height_min: number;
  height_max: number;
  length_min: number;
  length_max: number;
  n_anchors: number;
  n_pairs: number;
}

export type ZoneFeature = Feature<PolygonGeometry, ZoneProperties>;
export type ZoneFeatureCollection = FeatureCollection<ZoneFeature>;

export interface DensityProperties {
  n_pairs: number;
  max_exposure: number;
  length_min: number | null;
  length_max: number | null;
}

export type DensityFeature = Feature<PolygonGeometry, DensityProperties>;
export type DensityFeatureCollection = FeatureCollection<DensityFeature>;

export type AnchorSector = [number, number, number];

export interface AnchorProperties {
  elev: number;
  sectors: AnchorSector[];
}

export type AnchorFeature = Feature<PointGeometry, AnchorProperties>;
export type AnchorFeatureCollection = FeatureCollection<AnchorFeature>;

export interface RestrictionLayerMeta {
  id: string;
  label: string;
  tooltip: string;
  highlight: string;
  color: string;
}

export interface RestrictionLayersResponse {
  layers: RestrictionLayerMeta[];
}

export interface RestrictionProperties {
  layer: string;
  name?: string;
}

export type RestrictionFeature = Feature<PolygonGeometry, RestrictionProperties>;
export type RestrictionFeatureCollection = FeatureCollection<RestrictionFeature>;
```

- [ ] **Step 3: Write helper tests**

Create `frontend/src/lib/geo.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { bboxLonLatParam, destPoint, initialViewFromSearch, wedge } from "./geo";

describe("initialViewFromSearch", () => {
  it("returns a valid view from lat/lng/z params", () => {
    expect(initialViewFromSearch("?lat=41.6&lng=1.83&z=13")).toEqual({
      center: [41.6, 1.83],
      zoom: 13,
    });
  });

  it("returns null when any view param is missing or invalid", () => {
    expect(initialViewFromSearch("?lat=41.6&lng=1.83")).toBeNull();
    expect(initialViewFromSearch("?lat=x&lng=1.83&z=13")).toBeNull();
  });
});

describe("bboxLonLatParam", () => {
  it("serializes west,south,east,north", () => {
    expect(
      bboxLonLatParam({
        getWest: () => 1,
        getSouth: () => 2,
        getEast: () => 3,
        getNorth: () => 4,
      }),
    ).toBe("1,2,3,4");
  });
});

describe("destPoint and wedge", () => {
  it("moves north for a zero-degree bearing", () => {
    const [lat, lon] = destPoint(41, 2, 0, 100);
    expect(lat).toBeGreaterThan(41);
    expect(lon).toBeCloseTo(2, 4);
  });

  it("creates a wedge with the apex as the first point", () => {
    const points = wedge(41, 2, 10, 40, 30);
    expect(points[0]).toEqual([41, 2]);
    expect(points.length).toBeGreaterThan(3);
  });
});
```

Create `frontend/src/lib/map-style.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ZoneFeature } from "@/types/highliner";
import { densityRank, tealShade, zoneKey } from "./map-style";

function zone(coords: [number, number][]): ZoneFeature {
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [coords] },
    properties: {
      height_min: 30,
      height_max: 60,
      length_min: 80,
      length_max: 120,
      n_anchors: 2,
      n_pairs: 1,
    },
  };
}

describe("tealShade", () => {
  it("returns hsl color strings", () => {
    expect(tealShade(0)).toBe("hsl(168, 45%, 88%)");
    expect(tealShade(1)).toBe("hsl(184, 70%, 26%)");
  });
});

describe("densityRank", () => {
  it("ranks values across sorted density counts", () => {
    expect(densityRank(10, [10, 20, 30])).toBe(0);
    expect(densityRank(20, [10, 20, 30])).toBe(0.5);
    expect(densityRank(30, [10, 20, 30])).toBe(1);
  });

  it("averages tied ranks", () => {
    expect(densityRank(20, [10, 20, 20, 40])).toBeCloseTo(0.5);
  });
});

describe("zoneKey", () => {
  it("dedupes nearby centroid-equivalent zones", () => {
    const a = zone([[1, 41], [1.001, 41], [1.001, 41.001], [1, 41.001], [1, 41]]);
    const b = zone([[1.00001, 41.00001], [1.00101, 41.00001], [1.00101, 41.00101], [1.00001, 41.00101], [1.00001, 41.00001]]);
    expect(zoneKey(a)).toBe(zoneKey(b));
  });
});
```

- [ ] **Step 4: Implement geo helpers**

Create `frontend/src/lib/geo.ts`:

```ts
export interface MapViewState {
  center: [number, number];
  zoom: number;
}

export interface LatLngBoundsLike {
  getWest(): number;
  getSouth(): number;
  getEast(): number;
  getNorth(): number;
}

export function initialViewFromSearch(search: string): MapViewState | null {
  const params = new URLSearchParams(search);
  const lat = Number.parseFloat(params.get("lat") ?? "");
  const lng = Number.parseFloat(params.get("lng") ?? "");
  const zoom = Number.parseFloat(params.get("z") ?? "");
  if (Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(zoom)) {
    return { center: [lat, lng], zoom };
  }
  return null;
}

export function bboxLonLatParam(bounds: LatLngBoundsLike): string {
  return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(",");
}

export function destPoint(lat: number, lon: number, bearingDeg: number, distM: number): [number, number] {
  const radiusM = 6_371_000;
  const d = distM / radiusM;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(bearing),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

export function wedge(
  lat: number,
  lon: number,
  start: number,
  end: number,
  radiusM = 30,
): [number, number][] {
  let span = (end - start) % 360;
  if (span <= 0) span += 360;
  const steps = Math.max(2, Math.ceil(span / 10));
  const points: [number, number][] = [[lat, lon]];
  for (let i = 0; i <= steps; i += 1) {
    points.push(destPoint(lat, lon, start + (span * i) / steps, radiusM));
  }
  return points;
}
```

- [ ] **Step 5: Implement map style helpers**

Create `frontend/src/lib/map-style.ts`:

```ts
import type { ZoneFeature } from "@/types/highliner";

export const ZONE_COLOR = "hsl(184, 70%, 26%)";
export const ANCHOR_COLOR = "#1f9e8f";
export const DENSITY_MAX_ZOOM = 12;
export const DENSITY_ZOOM_OFFSET = 2;
export const DENSITY_TILE_MIN = 6;
export const DENSITY_TILE_MAX = 14;
export const ANCHOR_MIN_ZOOM = 12;
export const ANCHOR_DETAIL_LIMIT = 400;
export const ANCHOR_WEDGE_RADIUS_M = 30;
export const ZONE_DEDUP_GRID_DEG = 0.0005;

export function tealShade(value: number): string {
  const t = Math.min(Math.max(value, 0), 1);
  const h = 168 + 16 * t;
  const s = 45 + 25 * t;
  const l = 88 - 62 * t;
  return `hsl(${h}, ${s}%, ${l}%)`;
}

export function densityRank(n: number, sorted: number[]): number {
  const m = sorted.length;
  if (m <= 1) return 1;
  let lo = 0;
  let hi = m;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < n) lo = mid + 1;
    else hi = mid;
  }
  let hiIdx = lo;
  while (hiIdx < m && sorted[hiIdx] === n) hiIdx += 1;
  return ((lo + hiIdx - 1) / 2) / (m - 1);
}

export function zoneKey(feature: ZoneFeature): string {
  const ring = feature.geometry.coordinates[0];
  let lon = 0;
  let lat = 0;
  for (const [x, y] of ring) {
    lon += x;
    lat += y;
  }
  lon /= ring.length;
  lat /= ring.length;
  return `${Math.round(lat / ZONE_DEDUP_GRID_DEG)}:${Math.round(lon / ZONE_DEDUP_GRID_DEG)}`;
}
```

- [ ] **Step 6: Verify helpers**

Run:

```bash
cd frontend
npm test -- src/lib/geo.test.ts src/lib/map-style.test.ts
npm run build
```

Expected: tests and build pass.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: add frontend helper utilities"
```

---

### Task 3: i18n Provider And Catalogs

**Files:**
- Create: `frontend/src/lib/i18n/strings.ts`
- Create: `frontend/src/lib/i18n/restrictionStrings.ts`
- Create: `frontend/src/lib/i18n/I18nProvider.tsx`
- Create: `frontend/src/lib/i18n/index.ts`
- Create: `frontend/src/lib/i18n/i18n.test.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `STRINGS` and `RESTRICTION_STRINGS` content from `web/i18n.js`.
- Produces:
  - `type Lang = "ca" | "es" | "en"`
  - `const LANGS: Lang[]`
  - `useI18n(): { lang: Lang; setLang(lang: Lang): void; t(key: StringKey, params?: Record<string, string | number>): string }`
  - `restrictionText(id: string, lang: Lang, fallback?: RestrictionText): RestrictionText`

- [ ] **Step 1: Write i18n tests**

Create `frontend/src/lib/i18n/i18n.test.tsx`:

```tsx
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReactNode } from "react";
import { I18nProvider, LANGS, STRINGS, restrictionText, useI18n } from "./index";

function wrapper({ children }: { children: ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>;
}

describe("catalog parity", () => {
  it("keeps every language on the Catalan key set", () => {
    const base = Object.keys(STRINGS.ca).sort();
    for (const lang of LANGS) {
      expect(Object.keys(STRINGS[lang]).sort()).toEqual(base);
    }
  });
});

describe("useI18n", () => {
  it("interpolates translated strings", () => {
    const { result } = renderHook(() => useI18n(), { wrapper });
    expect(result.current.t("zonesCount", { n: 3 })).toBe("3 zones");
  });

  it("switches language and updates document lang", () => {
    const { result } = renderHook(() => useI18n(), { wrapper });
    act(() => result.current.setLang("en"));
    expect(result.current.lang).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(result.current.t("searching")).toBe("searching...");
  });
});

describe("restrictionText", () => {
  const fallback = {
    label: "PEIN",
    tooltip: "Text en catala",
    highlight: "catala",
  };

  it("uses Catalan backend fallback for ca", () => {
    expect(restrictionText("pein", "ca", fallback)).toEqual(fallback);
  });

  it("uses frontend translation for en", () => {
    const text = restrictionText("pein", "en", fallback);
    expect(text.label).toBe("PEIN");
    expect(text.tooltip).toContain("Catalonia");
    expect(text.tooltip).toContain(text.highlight);
  });

  it("falls back to backend text for unknown layers", () => {
    expect(restrictionText("unknown", "en", fallback)).toEqual(fallback);
  });
});
```

- [ ] **Step 2: Port UI strings**

Create `frontend/src/lib/i18n/strings.ts` by copying the three `STRINGS` catalogs from `web/i18n.js` and changing syntax to TypeScript exports:

```ts
export const LANGS = ["ca", "es", "en"] as const;
export type Lang = (typeof LANGS)[number];

export const STRINGS = {
  ca: {
    language: "Idioma",
    panelMinimize: "Minimitza el panell",
    panelExpand: "Expandeix el panell",
    region: "Regio",
    maxLength: "Longitud maxima",
    minExposure: "Exposicio minima",
    showAnchors: "Mostra els ancoratges",
    restrictions: "Restriccions",
    caveat:
      "Zones per explorar - no s'ha confirmat que es puguin equipar. No s'han verificat ancoratges, arbres, roca solta, accessos ni permisos.",
    disclaimerTitle: "Abans de comencar",
    disclaimerLead: "Muntar una highline es perillos i pot ser mortal.",
    disclaimerBody:
      "Trobar i valorar un lloc es la part mes perillosa de l'highlining: aquesta eina nomes assenyala terreny que podria admetre una linia - mai no confirma ancoratges solids, accessos segurs, la qualitat de la roca ni que una linia es pugui equipar.",
    disclaimerResponsibility:
      "Ets l'unic responsable de valorar qualsevol lloc i de la teva propia seguretat. Highline Scout no es fa responsable de cap lesio, mort o dany derivat del seu us.",
    disclaimerAccept: "Ho entenc",
    searching: "cercant...",
    loadingHotspots: "carregant punts d'interes...",
    zonesCount: "{n} zones",
    hotspotCells: "{n} cel.les de punts d'interes (amplia per veure zones)",
    anchorsCount: "{n} ancoratges",
    protectedAreasCount: "{n} espais protegits",
    zoomInToSee: "amplia per veure {noun}",
    error: "error: {detail}",
    anchorError: "error d'ancoratges: {detail}",
    nounZones: "zones",
    nounHotspots: "punts d'interes",
    nounAnchors: "ancoratges",
    nounProtectedAreas: "espais protegits",
    zonePopup: "alcada {min}-{max} m<br>longitud {lmin}-{lmax} m<br>{na} ancoratges - {np} linies",
    densityTooltip: "{n} linies candidates - fins a {max} m{lenHint}",
    densityLenHint: " - {min}-{max} m de llarg",
    anchorPopup: "ancoratge - elev {elev} m<br>{sectors}",
    anchorSector: "caiguda {a}-{b} deg ({drop} m)",
    lineDensity: "Probabilitat de linies",
    sparse: "baixa",
    dense: "alta",
    viewInGoogleMaps: "Veure a Google Maps",
    copyLink: "Copia l'enllac",
    linkCopied: "Enllac copiat",
    openControls: "Obre controls",
    closeControls: "Tanca controls",
    filters: "Filtres",
    mapActions: "Accions del mapa",
  },
  es: {
    language: "Idioma",
    panelMinimize: "Minimizar panel",
    panelExpand: "Expandir panel",
    region: "Region",
    maxLength: "Longitud maxima",
    minExposure: "Exposicion minima",
    showAnchors: "Mostrar anclajes",
    restrictions: "Restricciones",
    caveat:
      "Zonas para explorar - no se ha confirmado que se puedan montar. No se han verificado anclajes, arboles, roca suelta, accesos ni permisos.",
    disclaimerTitle: "Antes de empezar",
    disclaimerLead: "Montar una highline es peligroso y puede ser mortal.",
    disclaimerBody:
      "Encontrar y valorar un sitio es la parte mas peligrosa del highlining: esta herramienta solo senala terreno que podria admitir una linea - nunca confirma anclajes solidos, accesos seguros, la calidad de la roca ni que una linea se pueda montar.",
    disclaimerResponsibility:
      "Eres el unico responsable de valorar cualquier sitio y de tu propia seguridad. Highline Scout no se hace responsable de ninguna lesion, muerte o dano derivado de su uso.",
    disclaimerAccept: "Lo entiendo",
    searching: "buscando...",
    loadingHotspots: "cargando puntos de interes...",
    zonesCount: "{n} zonas",
    hotspotCells: "{n} celdas de puntos de interes (amplia para ver zonas)",
    anchorsCount: "{n} anclajes",
    protectedAreasCount: "{n} espacios protegidos",
    zoomInToSee: "amplia para ver {noun}",
    error: "error: {detail}",
    anchorError: "error de anclajes: {detail}",
    nounZones: "zonas",
    nounHotspots: "puntos de interes",
    nounAnchors: "anclajes",
    nounProtectedAreas: "espacios protegidos",
    zonePopup: "altura {min}-{max} m<br>longitud {lmin}-{lmax} m<br>{na} anclajes - {np} lineas",
    densityTooltip: "{n} lineas candidatas - hasta {max} m{lenHint}",
    densityLenHint: " - {min}-{max} m de largo",
    anchorPopup: "anclaje - elev {elev} m<br>{sectors}",
    anchorSector: "caida {a}-{b} deg ({drop} m)",
    lineDensity: "Probabilidad de lineas",
    sparse: "baja",
    dense: "alta",
    viewInGoogleMaps: "Ver en Google Maps",
    copyLink: "Copiar enlace",
    linkCopied: "Enlace copiado",
    openControls: "Abrir controles",
    closeControls: "Cerrar controles",
    filters: "Filtros",
    mapActions: "Acciones del mapa",
  },
  en: {
    language: "Language",
    panelMinimize: "Minimize panel",
    panelExpand: "Expand panel",
    region: "Region",
    maxLength: "Max length",
    minExposure: "Min exposure",
    showAnchors: "Show anchors",
    restrictions: "Restrictions",
    caveat: "Zones to scout - not confirmed-riggable. No bolts, trees, loose rock, access or permissions are verified.",
    disclaimerTitle: "Before you scout",
    disclaimerLead: "Rigging a highline is dangerous and can be fatal.",
    disclaimerBody:
      "Finding and assessing a spot is the most dangerous part of highlining: this tool only points to terrain that might hold a line - it never confirms solid anchors, safe access, rock quality, or that a line can be rigged.",
    disclaimerResponsibility:
      "You alone are responsible for assessing any spot and for your own safety. Highline Scout accepts no liability for any injury, death, or damage arising from its use.",
    disclaimerAccept: "I understand",
    searching: "searching...",
    loadingHotspots: "loading hotspots...",
    zonesCount: "{n} zones",
    hotspotCells: "{n} hotspot cells (zoom in for zones)",
    anchorsCount: "{n} anchors",
    protectedAreasCount: "{n} protected areas",
    zoomInToSee: "zoom in to see {noun}",
    error: "error: {detail}",
    anchorError: "anchor error: {detail}",
    nounZones: "zones",
    nounHotspots: "hotspots",
    nounAnchors: "anchors",
    nounProtectedAreas: "protected areas",
    zonePopup: "height {min}-{max} m<br>length {lmin}-{lmax} m<br>{na} anchors - {np} lines",
    densityTooltip: "{n} candidate lines - up to {max} m{lenHint}",
    densityLenHint: " - {min}-{max} m long",
    anchorPopup: "anchor - elev {elev} m<br>{sectors}",
    anchorSector: "drop {a}-{b} deg ({drop} m)",
    lineDensity: "Line chance",
    sparse: "low",
    dense: "high",
    viewInGoogleMaps: "View in Google Maps",
    copyLink: "Copy link",
    linkCopied: "Link copied",
    openControls: "Open controls",
    closeControls: "Close controls",
    filters: "Filters",
    mapActions: "Map actions",
  },
} as const;

export type StringKey = keyof typeof STRINGS.ca;
```

Before implementation, compare this file against `web/i18n.js`. Preserve the same meanings. The snippet above intentionally uses ASCII punctuation to match repository editing constraints.

- [ ] **Step 3: Port restriction translations**

Create `frontend/src/lib/i18n/restrictionStrings.ts`:

```ts
import type { Lang } from "./strings";

export interface RestrictionText {
  label: string;
  tooltip: string;
  highlight: string;
}

export const RESTRICTION_STRINGS: Partial<Record<Lang, Record<string, RestrictionText>>> = {
  es: {
    pein: {
      label: "PEIN",
      tooltip:
        "Plan de Espacios de Interes Natural - el nivel basico de proteccion en Cataluna (Decreto 328/1992); incluye los espacios de la Red Natura 2000. Regimen urbanistico riguroso; las actividades que puedan lesionar los valores naturales pueden requerir evaluacion de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificacion de rapaces (aprox. enero-agosto, varia segun el espacio).",
      highlight:
        "las actividades que puedan lesionar los valores naturales pueden requerir evaluacion de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificacion de rapaces (aprox. enero-agosto, varia segun el espacio).",
    },
    parcs: {
      label: "Parques Naturales",
      tooltip:
        "El nivel de proteccion mas alto (ENPE), cada uno con su propio plan de gestion. Actividades como la escalada, el vivac, los drones y los actos organizados estan reguladas y a menudo necesitan autorizacion del organo gestor del parque.",
      highlight:
        "Actividades como la escalada, el vivac, los drones y los actos organizados estan reguladas y a menudo necesitan autorizacion del organo gestor del parque.",
    },
    fauna: {
      label: "Reservas de Fauna",
      tooltip:
        "Reserva Natural de Fauna Salvaje - protege la fauna. Se prohibe cualquier actividad que pueda perjudicar directa o indirectamente a la fauna protegida; consulte al organo gestor antes de realizar cualquier actividad.",
      highlight:
        "Se prohibe cualquier actividad que pueda perjudicar directa o indirectamente a la fauna protegida; consulte al organo gestor antes de realizar cualquier actividad.",
    },
  },
  en: {
    pein: {
      label: "PEIN",
      tooltip:
        "Plan for Areas of Natural Interest - Catalonia's baseline level of protection (Decree 328/1992); it includes the Natura 2000 network sites. Strict land-use regime; activities that may harm natural values can require an environmental impact assessment. Many cliffs have seasonal climbing closures for raptor nesting (roughly January-August, varies by site).",
      highlight:
        "activities that may harm natural values can require an environmental impact assessment. Many cliffs have seasonal climbing closures for raptor nesting (roughly January-August, varies by site).",
    },
    parcs: {
      label: "Nature Parks",
      tooltip:
        "The highest level of protection (ENPE), each with its own management plan. Activities such as climbing, bivouacking, drones and organized events are regulated and often need authorization from the park's managing body.",
      highlight:
        "Activities such as climbing, bivouacking, drones and organized events are regulated and often need authorization from the park's managing body.",
    },
    fauna: {
      label: "Wildlife Reserves",
      tooltip:
        "Wildlife Nature Reserve - protects fauna. Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
      highlight:
        "Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
    },
  },
};

export function restrictionText(id: string, lang: Lang, fallback?: RestrictionText): RestrictionText {
  return RESTRICTION_STRINGS[lang]?.[id] ?? fallback ?? { label: id, tooltip: "", highlight: "" };
}
```

- [ ] **Step 4: Implement provider**

Create `frontend/src/lib/i18n/I18nProvider.tsx`:

```tsx
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { LANGS, STRINGS, type Lang, type StringKey } from "./strings";

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: StringKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function isLang(value: string | null | undefined): value is Lang {
  return !!value && (LANGS as readonly string[]).includes(value);
}

function pickInitialLang(): Lang {
  try {
    const saved = window.localStorage.getItem("lang");
    if (isLang(saved)) return saved;
  } catch {
    // Storage can be unavailable in private mode.
  }

  const prefs = navigator.languages ?? [navigator.language ?? ""];
  for (const pref of prefs) {
    const code = pref.slice(0, 2).toLowerCase();
    if (isLang(code)) return code;
  }
  return "ca";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => pickInitialLang());

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      window.localStorage.setItem("lang", lang);
    } catch {
      // Ignore unavailable storage.
    }
  }, [lang]);

  const value = useMemo<I18nContextValue>(() => {
    return {
      lang,
      setLang: setLangState,
      t: (key, params) => {
        let value = STRINGS[lang][key] ?? key;
        if (params) {
          value = value.replace(/\{(\w+)\}/g, (match, name) =>
            Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
          );
        }
        return value;
      },
    };
  }, [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
```

Create `frontend/src/lib/i18n/index.ts`:

```ts
export { I18nProvider, useI18n } from "./I18nProvider";
export { LANGS, STRINGS, type Lang, type StringKey } from "./strings";
export { RESTRICTION_STRINGS, restrictionText, type RestrictionText } from "./restrictionStrings";
```

- [ ] **Step 5: Wrap the app**

Modify `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/globals.css";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
);
```

Modify `frontend/src/App.tsx`:

```tsx
import { useI18n } from "./lib/i18n";

export function App() {
  const { t } = useI18n();
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <h1 className="text-lg font-semibold">Highline Scout</h1>
      <span className="sr-only">{t("language")}</span>
    </main>
  );
}
```

- [ ] **Step 6: Verify i18n**

Run:

```bash
cd frontend
npm test -- src/lib/i18n/i18n.test.tsx
npm run build
```

Expected: tests and build pass.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: port frontend i18n"
```

---

### Task 4: Typed API Client

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Consumes: types from `frontend/src/types/highliner.ts`.
- Produces:
  - `fetchRegions(signal?: AbortSignal): Promise<Region[]>`
  - `fetchZones(params: ZoneQuery, signal?: AbortSignal): Promise<ZoneFeatureCollection>`
  - `fetchDensity(params: DensityQuery, signal?: AbortSignal): Promise<DensityFeatureCollection>`
  - `fetchAnchors(params: ViewportQuery, signal?: AbortSignal): Promise<AnchorFeatureCollection>`
  - `fetchRestrictionLayers(signal?: AbortSignal): Promise<RestrictionLayerMeta[]>`
  - `fetchRestrictions(params: RestrictionsQuery, signal?: AbortSignal): Promise<RestrictionFeatureCollection>`
  - `ApiError` with `status` and `detail`.

- [ ] **Step 1: Write API client tests**

Create `frontend/src/lib/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchRegions, fetchZones } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("fetches regions and unwraps the response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ regions: [{ name: "cat", bounds_lonlat: [1, 2, 3, 4] }] }),
      }),
    );

    await expect(fetchRegions()).resolves.toEqual([{ name: "cat", bounds_lonlat: [1, 2, 3, 4] }]);
    expect(fetch).toHaveBeenCalledWith("/regions", { signal: undefined });
  });

  it("serializes zone query params", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ type: "FeatureCollection", features: [] }),
      }),
    );

    await fetchZones({
      region: "catalonia",
      bboxLonLat: "1,2,3,4",
      maxLen: 150,
      minExposure: 30,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/zones?region=catalonia&bbox_lonlat=1%2C2%2C3%2C4&max_len=150&min_exposure=30",
      { signal: undefined },
    );
  });

  it("raises ApiError with backend detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
        json: async () => ({ detail: "too many" }),
      }),
    );

    await expect(fetchRegions()).rejects.toMatchObject(new ApiError(413, "too many"));
  });
});
```

- [ ] **Step 2: Implement API client**

Create `frontend/src/lib/api.ts`:

```ts
import type {
  AnchorFeatureCollection,
  DensityFeatureCollection,
  Region,
  RegionsResponse,
  RestrictionFeatureCollection,
  RestrictionLayerMeta,
  RestrictionLayersResponse,
  ZoneFeatureCollection,
} from "@/types/highliner";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export interface ViewportQuery {
  region: string;
  bboxLonLat: string;
}

export interface ZoneQuery extends ViewportQuery {
  maxLen: number;
  minExposure: number;
}

export interface DensityQuery extends ViewportQuery {
  z: number;
}

export interface RestrictionsQuery {
  bboxLonLat: string;
  layers: string[];
}

async function parseError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : String(response.status);
  return new ApiError(response.status, detail);
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number>): string {
  return new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)])).toString();
}

export async function fetchRegions(signal?: AbortSignal): Promise<Region[]> {
  const response = await fetchJson<RegionsResponse>("/regions", signal);
  return response.regions;
}

export function fetchZones(params: ZoneQuery, signal?: AbortSignal): Promise<ZoneFeatureCollection> {
  return fetchJson(
    `/zones?${query({
      region: params.region,
      bbox_lonlat: params.bboxLonLat,
      max_len: params.maxLen,
      min_exposure: params.minExposure,
    })}`,
    signal,
  );
}

export function fetchDensity(params: DensityQuery, signal?: AbortSignal): Promise<DensityFeatureCollection> {
  return fetchJson(
    `/density?${query({
      region: params.region,
      z: params.z,
      bbox_lonlat: params.bboxLonLat,
    })}`,
    signal,
  );
}

export function fetchAnchors(params: ViewportQuery, signal?: AbortSignal): Promise<AnchorFeatureCollection> {
  return fetchJson(`/anchors?${query({ region: params.region, bbox_lonlat: params.bboxLonLat })}`, signal);
}

export async function fetchRestrictionLayers(signal?: AbortSignal): Promise<RestrictionLayerMeta[]> {
  const response = await fetchJson<RestrictionLayersResponse>("/restrictions/layers", signal);
  return response.layers;
}

export function fetchRestrictions(
  params: RestrictionsQuery,
  signal?: AbortSignal,
): Promise<RestrictionFeatureCollection> {
  return fetchJson(
    `/restrictions?${query({
      bbox_lonlat: params.bboxLonLat,
      layers: params.layers.join(","),
    })}`,
    signal,
  );
}
```

- [ ] **Step 3: Verify API client**

Run:

```bash
cd frontend
npm test -- src/lib/api.test.ts
npm run build
```

Expected: tests and build pass.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat: add typed frontend api client"
```

---

### Task 5: Responsive Shell And Control Components

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/DesktopSidebar.tsx`
- Create: `frontend/src/components/MobileControlSheet.tsx`
- Create: `frontend/src/components/FilterControls.tsx`
- Create: `frontend/src/components/LanguageSwitcher.tsx`
- Create: `frontend/src/components/RestrictionLayerControls.tsx`
- Create: `frontend/src/components/StatusLine.tsx`
- Create: `frontend/src/components/SafetyDisclaimerDialog.tsx`
- Create: `frontend/src/components/AppShell.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/globals.css`

**Interfaces:**
- Consumes: i18n provider, shadcn primitives, API types.
- Produces:
  - `AppState` in `App.tsx`: region, filters, anchors toggle, restrictions, status messages.
  - `AppShell` accepts controls and map slots.
  - `FilterControls` emits `onMaxLenCommit` and `onMinExposureCommit`.

- [ ] **Step 1: Write shell tests**

Create `frontend/src/components/AppShell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { AppShell } from "./AppShell";

function renderShell() {
  return render(
    <I18nProvider>
      <AppShell
        sidebar={<div>sidebar controls</div>}
        mobileControls={<div>mobile controls</div>}
        map={<div>map area</div>}
      />
    </I18nProvider>,
  );
}

describe("AppShell", () => {
  it("renders desktop sidebar, mobile controls, and map slots", () => {
    renderShell();
    expect(screen.getByText("sidebar controls")).toBeInTheDocument();
    expect(screen.getByText("mobile controls")).toBeInTheDocument();
    expect(screen.getByText("map area")).toBeInTheDocument();
  });

  it("toggles desktop sidebar collapsed state", async () => {
    const user = userEvent.setup();
    renderShell();
    const button = screen.getByRole("button", { name: /minimize|minimitza|minimizar/i });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
```

- [ ] **Step 2: Implement AppShell**

Create `frontend/src/components/AppShell.tsx`:

```tsx
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

interface AppShellProps {
  sidebar: ReactNode;
  mobileControls: ReactNode;
  map: ReactNode;
}

export function AppShell({ sidebar, mobileControls, map }: AppShellProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);
  const expanded = !collapsed;

  return (
    <div className="relative h-dvh overflow-hidden bg-background text-foreground">
      <aside
        className={cn(
          "absolute inset-y-0 left-0 z-[1000] hidden w-80 flex-col border-r bg-card shadow-sm transition-transform duration-200 md:flex",
          collapsed && "-translate-x-80",
        )}
      >
        {sidebar}
      </aside>
      <Button
        type="button"
        size="icon"
        variant="outline"
        aria-label={expanded ? t("panelMinimize") : t("panelExpand")}
        aria-expanded={expanded}
        className={cn(
          "absolute top-1/2 z-[1100] hidden h-14 w-8 -translate-y-1/2 rounded-l-none rounded-r-md bg-card md:inline-flex",
          expanded ? "left-80 -ml-px" : "left-0",
        )}
        onClick={() => setCollapsed((value) => !value)}
      >
        {expanded ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
      </Button>
      <main className={cn("h-full transition-[padding] duration-200 md:pl-80", collapsed && "md:pl-0")}>
        {map}
      </main>
      <div className="md:hidden">{mobileControls}</div>
    </div>
  );
}
```

- [ ] **Step 3: Implement presentational controls**

Create `frontend/src/components/StatusLine.tsx`:

```tsx
export function StatusLine({ children }: { children?: string }) {
  if (!children) return null;
  return <p className="text-xs leading-5 text-muted-foreground">{children}</p>;
}
```

Create `frontend/src/components/LanguageSwitcher.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { LANGS, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LABELS: Record<Lang, string> = { ca: "CA", es: "ES", en: "EN" };

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="space-y-2">
      {!compact && <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{t("language")}</div>}
      <div className="flex gap-1" role="group" aria-label={t("language")}>
        {LANGS.map((item) => (
          <Button
            key={item}
            type="button"
            size="sm"
            variant={item === lang ? "default" : "outline"}
            className={cn("h-8 px-3 text-xs", item === lang && "shadow-sm")}
            aria-pressed={item === lang}
            onClick={() => setLang(item)}
          >
            {LABELS[item]}
          </Button>
        ))}
      </div>
    </div>
  );
}
```

Create `frontend/src/components/FilterControls.tsx`:

```tsx
import type { Region } from "@/types/highliner";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useI18n } from "@/lib/i18n";

interface FilterControlsProps {
  regions: Region[];
  region: string;
  maxLen: number;
  minExposure: number;
  showAnchors: boolean;
  onRegionChange: (region: string) => void;
  onMaxLenChange: (value: number) => void;
  onMaxLenCommit: (value: number) => void;
  onMinExposureChange: (value: number) => void;
  onMinExposureCommit: (value: number) => void;
  onShowAnchorsChange: (value: boolean) => void;
}

export function FilterControls(props: FilterControlsProps) {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>{t("region")}</Label>
        <Select value={props.region} onValueChange={props.onRegionChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {props.regions.map((region) => (
              <SelectItem key={region.name} value={region.name}>
                {region.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("maxLength")}</Label>
          <span className="text-muted-foreground">{props.maxLen} m</span>
        </div>
        <Slider
          min={20}
          max={500}
          step={1}
          value={[props.maxLen]}
          onValueChange={([value]) => props.onMaxLenChange(value)}
          onValueCommit={([value]) => props.onMaxLenCommit(value)}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("minExposure")}</Label>
          <span className="text-muted-foreground">{props.minExposure} m</span>
        </div>
        <Slider
          min={0}
          max={300}
          step={1}
          value={[props.minExposure]}
          onValueChange={([value]) => props.onMinExposureChange(value)}
          onValueCommit={([value]) => props.onMinExposureCommit(value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={props.showAnchors} onCheckedChange={(value) => props.onShowAnchorsChange(value === true)} />
        <span>{t("showAnchors")}</span>
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Implement sidebar and mobile sheet**

Create `frontend/src/components/DesktopSidebar.tsx`:

```tsx
import type { ReactNode } from "react";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface DesktopSidebarProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
}

export function DesktopSidebar({ filters, restrictions, statuses, caveat }: DesktopSidebarProps) {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Highline Scout</h1>
      </div>
      {filters}
      {statuses}
      {restrictions}
      <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">{caveat}</p>
      <div className="mt-auto border-t pt-4">
        <LanguageSwitcher />
      </div>
    </div>
  );
}
```

Create `frontend/src/components/MobileControlSheet.tsx`:

```tsx
import type { ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface MobileControlSheetProps {
  region?: string;
  summary: string;
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
  actions: ReactNode;
}

export function MobileControlSheet(props: MobileControlSheetProps) {
  const { t } = useI18n();
  return (
    <Sheet>
      <div className="fixed inset-x-3 bottom-3 z-[1100] rounded-xl border bg-card/95 p-3 shadow-xl backdrop-blur">
        <div className="mb-2 h-1 w-10 rounded-full bg-border mx-auto" />
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{props.region || "Highline Scout"}</div>
            <div className="truncate text-xs text-muted-foreground">{props.summary}</div>
          </div>
          <SheetTrigger asChild>
            <Button type="button" size="sm" aria-label={t("openControls")}>
              <SlidersHorizontal className="mr-2 h-4 w-4" />
              {t("filters")}
            </Button>
          </SheetTrigger>
        </div>
      </div>
      <SheetContent side="bottom" className="max-h-[88dvh] overflow-y-auto rounded-t-2xl">
        <SheetHeader>
          <SheetTitle>{t("filters")}</SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-5">
          {props.filters}
          {props.statuses}
          {props.actions}
          {props.restrictions}
          <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">{props.caveat}</p>
          <LanguageSwitcher compact />
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 5: Implement restrictions controls and disclaimer**

Create `frontend/src/components/RestrictionLayerControls.tsx`:

```tsx
import type { RestrictionLayerMeta } from "@/types/highliner";
import { Checkbox } from "@/components/ui/checkbox";
import { useI18n, restrictionText } from "@/lib/i18n";

interface RestrictionLayerControlsProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
  onEnabledChange: (enabled: string[]) => void;
}

function HighlightedText({ text, highlight }: { text: string; highlight: string }) {
  const index = highlight ? text.indexOf(highlight) : -1;
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded bg-yellow-100 px-0.5 font-semibold text-inherit">{highlight}</mark>
      {text.slice(index + highlight.length)}
    </>
  );
}

export function RestrictionLayerControls({ layers, enabled, onEnabledChange }: RestrictionLayerControlsProps) {
  const { lang, t } = useI18n();
  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-xs font-medium text-muted-foreground">{t("restrictions")}</legend>
      {layers.map((layer) => {
        const checked = enabled.includes(layer.id);
        const tx = restrictionText(layer.id, lang, layer);
        return (
          <div key={layer.id} className="space-y-1">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={checked}
                onCheckedChange={(value) => {
                  const next = value === true ? [...enabled, layer.id] : enabled.filter((id) => id !== layer.id);
                  onEnabledChange(next);
                }}
              />
              <span className="h-3 w-3 border" style={{ backgroundColor: layer.color }} />
              <span>{tx.label}</span>
            </label>
            {checked && (
              <p className="pl-7 text-xs leading-5 text-muted-foreground">
                <HighlightedText text={tx.tooltip} highlight={tx.highlight} />
              </p>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}
```

Create `frontend/src/components/SafetyDisclaimerDialog.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface SafetyDisclaimerDialogProps {
  open: boolean;
  onAccept: () => void;
}

export function SafetyDisclaimerDialog({ open, onAccept }: SafetyDisclaimerDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open}>
      <DialogContent hideClose className="sm:max-w-md">
        <div className="flex justify-end">
          <LanguageSwitcher compact />
        </div>
        <DialogHeader>
          <DialogTitle>{t("disclaimerTitle")}</DialogTitle>
          <DialogDescription className="space-y-3 text-left">
            <span className="block font-semibold text-destructive">{t("disclaimerLead")}</span>
            <span className="block">{t("disclaimerBody")}</span>
            <span className="block">{t("disclaimerResponsibility")}</span>
          </DialogDescription>
        </DialogHeader>
        <Button type="button" onClick={onAccept} autoFocus>
          {t("disclaimerAccept")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
```

If the generated shadcn `DialogContent` does not accept `hideClose`, add that optional prop in `frontend/src/components/ui/dialog.tsx` and render the close button only when `!hideClose`.

- [ ] **Step 6: Wire app state without map data yet**

Modify `frontend/src/App.tsx`:

```tsx
import { useMemo, useState } from "react";
import { AppShell } from "./components/AppShell";
import { DesktopSidebar } from "./components/DesktopSidebar";
import { FilterControls } from "./components/FilterControls";
import { MobileControlSheet } from "./components/MobileControlSheet";
import { RestrictionLayerControls } from "./components/RestrictionLayerControls";
import { SafetyDisclaimerDialog } from "./components/SafetyDisclaimerDialog";
import { StatusLine } from "./components/StatusLine";
import { Button } from "./components/ui/button";
import { useI18n } from "./lib/i18n";
import type { Region, RestrictionLayerMeta } from "./types/highliner";

export function App() {
  const { t } = useI18n();
  const [regions] = useState<Region[]>([]);
  const [region, setRegion] = useState("");
  const [maxLen, setMaxLen] = useState(150);
  const [minExposure, setMinExposure] = useState(30);
  const [showAnchors, setShowAnchors] = useState(true);
  const [restrictionLayers] = useState<RestrictionLayerMeta[]>([]);
  const [enabledRestrictions, setEnabledRestrictions] = useState<string[]>([]);
  const [disclaimerOpen, setDisclaimerOpen] = useState(true);

  const filters = (
    <FilterControls
      regions={regions}
      region={region}
      maxLen={maxLen}
      minExposure={minExposure}
      showAnchors={showAnchors}
      onRegionChange={setRegion}
      onMaxLenChange={setMaxLen}
      onMaxLenCommit={setMaxLen}
      onMinExposureChange={setMinExposure}
      onMinExposureCommit={setMinExposure}
      onShowAnchorsChange={setShowAnchors}
    />
  );
  const statuses = (
    <div className="space-y-1">
      <StatusLine>{t("zoomInToSee", { noun: t("nounZones") })}</StatusLine>
    </div>
  );
  const restrictions = (
    <RestrictionLayerControls
      layers={restrictionLayers}
      enabled={enabledRestrictions}
      onEnabledChange={setEnabledRestrictions}
    />
  );
  const summary = useMemo(() => `${t("maxLength")} ${maxLen} m - ${t("minExposure")} ${minExposure} m`, [t, maxLen, minExposure]);

  return (
    <>
      <AppShell
        sidebar={<DesktopSidebar filters={filters} statuses={statuses} restrictions={restrictions} caveat={t("caveat")} />}
        mobileControls={
          <MobileControlSheet
            region={region}
            summary={summary}
            filters={filters}
            statuses={statuses}
            restrictions={restrictions}
            caveat={t("caveat")}
            actions={<Button variant="outline">{t("mapActions")}</Button>}
          />
        }
        map={<div className="flex h-full items-center justify-center bg-secondary text-sm text-muted-foreground">Map loading</div>}
      />
      <SafetyDisclaimerDialog open={disclaimerOpen} onAccept={() => setDisclaimerOpen(false)} />
    </>
  );
}
```

- [ ] **Step 7: Verify shell**

Run:

```bash
cd frontend
npm test -- src/components/AppShell.test.tsx
npm run build
```

Expected: tests and build pass.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat: build responsive frontend shell"
```

---

### Task 6: Regions Loading And Base Leaflet Map

**Files:**
- Create: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/globals.css`

**Interfaces:**
- Consumes: `fetchRegions`, `initialViewFromSearch`.
- Produces:
  - `MapView` props: regions, selected region, `onViewportChange`, `onMapReady`.
  - Region selection fits bounds unless URL view was used.

- [ ] **Step 1: Implement base MapView**

Create `frontend/src/components/map/MapView.tsx`:

```tsx
import L from "leaflet";
import { useEffect, useRef } from "react";
import { initialViewFromSearch, type MapViewState } from "@/lib/geo";
import type { Region } from "@/types/highliner";

const DEFAULT_VIEW: MapViewState = { center: [41.6, 1.83], zoom: 13 };

interface MapViewProps {
  regions: Region[];
  region: string;
  onViewportChange: (map: L.Map) => void;
}

export function MapView({ regions, region, onViewportChange }: MapViewProps) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const usedUrlViewRef = useRef(false);

  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const urlView = initialViewFromSearch(window.location.search);
    usedUrlViewRef.current = !!urlView;
    const view = urlView ?? DEFAULT_VIEW;
    const map = L.map(elRef.current).setView(view.center, view.zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "(c) OpenStreetMap",
    }).addTo(map);
    map.on("moveend", () => onViewportChange(map));
    mapRef.current = map;
    onViewportChange(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [onViewportChange]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region || usedUrlViewRef.current) {
      usedUrlViewRef.current = false;
      return;
    }
    const selected = regions.find((item) => item.name === region);
    if (!selected) return;
    const [w, s, e, n] = selected.bounds_lonlat;
    map.fitBounds([
      [s, w],
      [n, e],
    ]);
  }, [region, regions]);

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 250);
    return () => window.clearTimeout(timeout);
  });

  return <div ref={elRef} className="h-full w-full" />;
}
```

- [ ] **Step 2: Wire region loading in App**

Modify `frontend/src/App.tsx` so it loads regions:

```tsx
// add imports
import { useCallback, useEffect, useMemo, useState } from "react";
import type L from "leaflet";
import { fetchRegions } from "./lib/api";
import { MapView } from "./components/map/MapView";
import { bboxLonLatParam } from "./lib/geo";

// inside App, replace region state block
const [regions, setRegions] = useState<Region[]>([]);
const [region, setRegion] = useState("");
const [mapStatus, setMapStatus] = useState("");
const [viewportBbox, setViewportBbox] = useState("");

useEffect(() => {
  const controller = new AbortController();
  fetchRegions(controller.signal)
    .then((items) => {
      setRegions(items);
      if (!region && items[0]) setRegion(items[0].name);
    })
    .catch((error) => {
      if (error.name !== "AbortError") setMapStatus(t("error", { detail: error.detail ?? String(error) }));
    });
  return () => controller.abort();
}, [region, t]);

const handleViewportChange = useCallback((map: L.Map) => {
  setViewportBbox(bboxLonLatParam(map.getBounds()));
}, []);
```

Replace the map slot with:

```tsx
map={<MapView regions={regions} region={region} onViewportChange={handleViewportChange} />}
```

Add `mapStatus` into statuses:

```tsx
<StatusLine>{mapStatus || (viewportBbox ? "" : t("searching"))}</StatusLine>
```

- [ ] **Step 3: Verify map boot**

Run:

```bash
cd frontend
npm run build
```

Then run both dev servers:

```bash
just dev
cd frontend && npm run dev
```

Expected: visiting Vite URL shows the map and the sidebar/sheet. Region list loads when backend has `data/<region>/grid.json`.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat: load regions and render base map"
```

---

### Task 7: Zones And Density Layers

**Files:**
- Create: `frontend/src/components/map/popups.ts`
- Create: `frontend/src/components/map/leafletLayers.ts`
- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchZones`, `fetchDensity`, `zoneKey`, `densityRank`, `tealShade`, i18n.
- Produces: Leaflet zone layer, density layer, density legend state, zone count/status.

- [ ] **Step 1: Add popup builders**

Create `frontend/src/components/map/popups.ts`:

```ts
import type { AnchorProperties, DensityProperties, ZoneProperties } from "@/types/highliner";
import type { StringKey } from "@/lib/i18n";

type T = (key: StringKey, params?: Record<string, string | number>) => string;

export function zonePopupHtml(p: ZoneProperties, t: T): string {
  return t("zonePopup", {
    min: p.height_min,
    max: p.height_max,
    lmin: Math.round(p.length_min),
    lmax: Math.round(p.length_max),
    na: p.n_anchors,
    np: p.n_pairs,
  });
}

export function densityTooltipHtml(p: DensityProperties, t: T): string {
  const lenHint =
    p.length_min == null || p.length_max == null
      ? ""
      : t("densityLenHint", { min: Math.round(p.length_min), max: Math.round(p.length_max) });
  return t("densityTooltip", { n: p.n_pairs, max: Math.round(p.max_exposure), lenHint });
}

export function anchorPopupHtml(p: AnchorProperties, t: T): string {
  const sectors = p.sectors
    .map((s) => t("anchorSector", { a: Math.round(s[0]), b: Math.round(s[1]), drop: Math.round(s[2]) }))
    .join("<br>");
  return t("anchorPopup", { elev: Math.round(p.elev), sectors });
}
```

- [ ] **Step 2: Add layer helper**

Create `frontend/src/components/map/leafletLayers.ts`:

```ts
import L from "leaflet";
import { densityRank, tealShade, ZONE_COLOR } from "@/lib/map-style";
import type { DensityFeature, ZoneFeature } from "@/types/highliner";
import { densityTooltipHtml, zonePopupHtml } from "./popups";
import type { StringKey } from "@/lib/i18n";

type T = (key: StringKey, params?: Record<string, string | number>) => string;

export function createZoneLayer(t: T): L.GeoJSON {
  return L.geoJSON(undefined, {
    style: () => ({
      color: ZONE_COLOR,
      weight: 2,
      fillOpacity: 0.35,
    }),
    onEachFeature: (feature, layer) => {
      const zone = feature as ZoneFeature;
      layer.bindPopup(zonePopupHtml(zone.properties, t));
    },
  });
}

export function createDensityLayer(t: T, sortedCounts: () => number[]): L.GeoJSON {
  return L.geoJSON(undefined, {
    style: (feature) => {
      const density = feature as DensityFeature;
      const rank = densityRank(density.properties.n_pairs, sortedCounts());
      return {
        color: tealShade(Math.min(rank + 0.15, 1)),
        weight: 0.5,
        fillColor: tealShade(rank),
        fillOpacity: 0.2 + 0.55 * rank,
      };
    },
    onEachFeature: (feature, layer) => {
      const density = feature as DensityFeature;
      layer.bindTooltip(densityTooltipHtml(density.properties, t));
    },
  });
}
```

- [ ] **Step 3: Extend MapView for zone/density rendering**

Modify `frontend/src/components/map/MapView.tsx` props:

```ts
interface MapViewProps {
  regions: Region[];
  region: string;
  maxLen: number;
  minExposure: number;
  onViewportChange: (map: L.Map) => void;
  onMapStatus: (status: string) => void;
}
```

Add imports:

```ts
import { useI18n } from "@/lib/i18n";
import { ApiError, fetchDensity, fetchZones } from "@/lib/api";
import { bboxLonLatParam } from "@/lib/geo";
import { DENSITY_MAX_ZOOM, DENSITY_TILE_MAX, DENSITY_TILE_MIN, DENSITY_ZOOM_OFFSET, zoneKey } from "@/lib/map-style";
import { createDensityLayer, createZoneLayer } from "./leafletLayers";
```

Inside `MapView`, create refs:

```ts
const { t } = useI18n();
const zoneLayerRef = useRef<L.GeoJSON | null>(null);
const densityLayerRef = useRef<L.GeoJSON | null>(null);
const shownZoneKeysRef = useRef(new Set<string>());
const densitySortedRef = useRef<number[]>([]);
const requestIdRef = useRef(0);
```

After base map creation, add layers:

```ts
zoneLayerRef.current = createZoneLayer(t).addTo(map);
densityLayerRef.current = createDensityLayer(t, () => densitySortedRef.current).addTo(map);
```

Add a data-loading effect:

```tsx
useEffect(() => {
  const map = mapRef.current;
  if (!map || !region) return;
  const requestId = (requestIdRef.current += 1);
  const controller = new AbortController();
  const bboxLonLat = bboxLonLatParam(map.getBounds());

  async function load() {
    if (!map) return;
    const zoom = map.getZoom();
    onMapStatus(zoom <= DENSITY_MAX_ZOOM ? t("loadingHotspots") : t("searching"));
    try {
      if (zoom <= DENSITY_MAX_ZOOM) {
        zoneLayerRef.current?.clearLayers();
        shownZoneKeysRef.current.clear();
        const z = Math.min(Math.max(Math.round(zoom) + DENSITY_ZOOM_OFFSET, DENSITY_TILE_MIN), DENSITY_TILE_MAX);
        const fc = await fetchDensity({ region, z, bboxLonLat }, controller.signal);
        if (requestId !== requestIdRef.current) return;
        densityLayerRef.current?.clearLayers();
        densitySortedRef.current = fc.features.map((feature) => feature.properties.n_pairs).sort((a, b) => a - b);
        densityLayerRef.current?.addData(fc);
        onMapStatus(t("hotspotCells", { n: fc.features.length }));
        return;
      }

      densityLayerRef.current?.clearLayers();
      const fc = await fetchZones({ region, bboxLonLat, maxLen, minExposure }, controller.signal);
      if (requestId !== requestIdRef.current) return;
      const fresh = fc.features.filter((feature) => {
        const key = zoneKey(feature);
        if (shownZoneKeysRef.current.has(key)) return false;
        shownZoneKeysRef.current.add(key);
        return true;
      });
      zoneLayerRef.current?.addData({ type: "FeatureCollection", features: fresh });
      onMapStatus(t("zonesCount", { n: shownZoneKeysRef.current.size }));
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 413) {
        onMapStatus(t("zoomInToSee", { noun: t(map.getZoom() <= DENSITY_MAX_ZOOM ? "nounHotspots" : "nounZones") }));
      } else {
        onMapStatus(t("error", { detail: error instanceof Error ? error.message : String(error) }));
      }
    }
  }

  load();
  return () => controller.abort();
}, [region, maxLen, minExposure, t, onMapStatus]);
```

On region/filter reset, clear zones:

```tsx
useEffect(() => {
  zoneLayerRef.current?.clearLayers();
  shownZoneKeysRef.current.clear();
}, [region, maxLen, minExposure]);
```

In the `moveend` handler, call `onViewportChange(map)` and update a local `viewportTick` state so the data-loading effect runs after pans.

- [ ] **Step 4: Wire map status in App**

Modify the `MapView` usage:

```tsx
map={
  <MapView
    regions={regions}
    region={region}
    maxLen={maxLen}
    minExposure={minExposure}
    onViewportChange={handleViewportChange}
    onMapStatus={setMapStatus}
  />
}
```

Ensure the map status appears in both desktop and mobile statuses:

```tsx
<StatusLine>{mapStatus}</StatusLine>
```

- [ ] **Step 5: Verify zones/density**

Run:

```bash
cd frontend
npm run build
```

Manual check with data present:

```bash
just dev
cd frontend && npm run dev
```

Expected:

- Zoom `<= 12` shows density cells and status text.
- Zoom `> 12` shows zones.
- Panning in zone mode accumulates zones.
- Changing either slider clears old accumulated zones and reloads.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: render zones and density in react map"
```

---

### Task 8: Anchors, Restrictions, And Map Actions

**Files:**
- Modify: `frontend/src/components/map/leafletLayers.ts`
- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchAnchors`, `fetchRestrictionLayers`, `fetchRestrictions`, `wedge`, `restrictionText`.
- Produces: anchor layer, restriction layer, mobile map actions, link copy status.

- [ ] **Step 1: Extend layer helpers for anchors and restrictions**

Add to `frontend/src/components/map/leafletLayers.ts`:

```ts
import { ANCHOR_COLOR, ANCHOR_DETAIL_LIMIT, ANCHOR_WEDGE_RADIUS_M } from "@/lib/map-style";
import { wedge } from "@/lib/geo";
import type { AnchorFeatureCollection, RestrictionFeature, RestrictionLayerMeta } from "@/types/highliner";
import { anchorPopupHtml } from "./popups";

export function renderAnchors(layer: L.LayerGroup, fc: AnchorFeatureCollection, t: T): void {
  layer.clearLayers();
  const detailed = fc.features.length <= ANCHOR_DETAIL_LIMIT;
  const canvas = L.canvas({ padding: 0.5 });
  for (const feature of fc.features) {
    const [lon, lat] = feature.geometry.coordinates;
    if (detailed) {
      for (const sector of feature.properties.sectors) {
        L.polygon(wedge(lat, lon, sector[0], sector[1], ANCHOR_WEDGE_RADIUS_M), {
          color: ANCHOR_COLOR,
          weight: 1,
          fillOpacity: 0.25,
        }).addTo(layer);
      }
      L.circleMarker([lat, lon], {
        radius: 4,
        color: ANCHOR_COLOR,
        weight: 1,
        fillOpacity: 1,
      })
        .bindPopup(anchorPopupHtml(feature.properties, t))
        .addTo(layer);
    } else {
      L.circleMarker([lat, lon], {
        renderer: canvas,
        radius: 2,
        color: ANCHOR_COLOR,
        weight: 1,
        fillOpacity: 0.8,
      })
        .bindPopup(anchorPopupHtml(feature.properties, t))
        .addTo(layer);
    }
  }
}

export function createRestrictionLayer(metaById: () => Map<string, RestrictionLayerMeta>): L.GeoJSON {
  return L.geoJSON(undefined, {
    pane: "restrictions",
    style: (feature) => {
      const restriction = feature as RestrictionFeature;
      return {
        color: metaById().get(restriction.properties.layer)?.color ?? "#888",
        weight: 1,
        fillOpacity: 0.15,
      };
    },
    onEachFeature: (feature, layer) => {
      const restriction = feature as RestrictionFeature;
      const meta = metaById().get(restriction.properties.layer);
      layer.bindPopup(`<b>${meta?.label ?? restriction.properties.layer}</b>${restriction.properties.name ? `<br>${restriction.properties.name}` : ""}`);
    },
  });
}
```

- [ ] **Step 2: Load restriction metadata in App**

In `frontend/src/App.tsx`, replace static restriction layer state with:

```tsx
const [restrictionLayers, setRestrictionLayers] = useState<RestrictionLayerMeta[]>([]);
const [restrictionStatus, setRestrictionStatus] = useState("");

useEffect(() => {
  const controller = new AbortController();
  fetchRestrictionLayers(controller.signal)
    .then(setRestrictionLayers)
    .catch((error) => {
      if (error.name !== "AbortError") setRestrictionStatus(t("error", { detail: error.detail ?? String(error) }));
    });
  return () => controller.abort();
}, [t]);
```

Add `restrictionStatus` to the statuses block.

- [ ] **Step 3: Extend MapView props and fetch anchors/restrictions**

Modify `MapViewProps`:

```ts
showAnchors: boolean;
enabledRestrictions: string[];
restrictionLayers: RestrictionLayerMeta[];
onAnchorStatus: (status: string) => void;
onRestrictionStatus: (status: string) => void;
```

Add refs:

```ts
const anchorLayerRef = useRef<L.LayerGroup | null>(null);
const restrictionLayerRef = useRef<L.GeoJSON | null>(null);
const restrictionMetaRef = useRef(new Map<string, RestrictionLayerMeta>());
```

After map creation:

```ts
map.createPane("restrictions");
const pane = map.getPane("restrictions");
if (pane) pane.style.zIndex = "350";
anchorLayerRef.current = L.layerGroup().addTo(map);
restrictionLayerRef.current = createRestrictionLayer(() => restrictionMetaRef.current).addTo(map);
```

Update `restrictionMetaRef` when props change:

```tsx
useEffect(() => {
  restrictionMetaRef.current = new Map(restrictionLayers.map((layer) => [layer.id, layer]));
}, [restrictionLayers]);
```

Add anchor loading effect:

```tsx
useEffect(() => {
  const map = mapRef.current;
  const layer = anchorLayerRef.current;
  if (!map || !layer || !region) return;
  if (!showAnchors) {
    layer.clearLayers();
    onAnchorStatus("");
    return;
  }
  if (map.getZoom() < ANCHOR_MIN_ZOOM) {
    layer.clearLayers();
    onAnchorStatus(t("zoomInToSee", { noun: t("nounAnchors") }));
    return;
  }
  const controller = new AbortController();
  fetchAnchors({ region, bboxLonLat: bboxLonLatParam(map.getBounds()) }, controller.signal)
    .then((fc) => {
      renderAnchors(layer, fc, t);
      onAnchorStatus(t("anchorsCount", { n: fc.features.length }));
    })
    .catch((error) => {
      if (controller.signal.aborted) return;
      layer.clearLayers();
      onAnchorStatus(t("anchorError", { detail: error instanceof Error ? error.message : String(error) }));
    });
  return () => controller.abort();
}, [region, showAnchors, t, onAnchorStatus]);
```

Add restrictions loading effect:

```tsx
useEffect(() => {
  const map = mapRef.current;
  const layer = restrictionLayerRef.current;
  if (!map || !layer) return;
  if (enabledRestrictions.length === 0) {
    layer.clearLayers();
    onRestrictionStatus("");
    return;
  }
  const controller = new AbortController();
  fetchRestrictions(
    { bboxLonLat: bboxLonLatParam(map.getBounds()), layers: enabledRestrictions },
    controller.signal,
  )
    .then((fc) => {
      layer.clearLayers();
      layer.addData(fc);
      onRestrictionStatus(t("protectedAreasCount", { n: fc.features.length }));
    })
    .catch((error) => {
      if (controller.signal.aborted) return;
      layer.clearLayers();
      if (error instanceof ApiError && error.status === 413) {
        onRestrictionStatus(t("zoomInToSee", { noun: t("nounProtectedAreas") }));
      } else {
        onRestrictionStatus(t("error", { detail: error instanceof Error ? error.message : String(error) }));
      }
    });
  return () => controller.abort();
}, [enabledRestrictions, t, onRestrictionStatus]);
```

Include the same `viewportTick` used for zones in both effects so moving the map refreshes anchors and restrictions.

- [ ] **Step 4: Add map actions**

In `MapView`, add context menu:

```ts
map.on("contextmenu", (event) => {
  const { lat, lng } = event.latlng;
  const zoom = map.getZoom();
  const container = L.DomUtil.create("div", "map-context-menu");
  const gmaps = L.DomUtil.create("a", "", container);
  gmaps.href = `https://www.google.com/maps?q=${lat},${lng}`;
  gmaps.target = "_blank";
  gmaps.rel = "noopener";
  gmaps.textContent = t("viewInGoogleMaps");
  const copy = L.DomUtil.create("button", "", container);
  copy.type = "button";
  copy.textContent = t("copyLink");
  L.DomEvent.on(copy, "click", () => copyViewportLink(lat, lng, zoom, t));
  L.popup().setLatLng(event.latlng).setContent(container).openOn(map);
});
```

Add helper in `MapView.tsx`:

```ts
async function copyViewportLink(lat: number, lng: number, zoom: number, t: T) {
  const params = new URLSearchParams({ lat: lat.toFixed(5), lng: lng.toFixed(5), z: String(zoom) });
  const url = `${window.location.origin}${window.location.pathname}?${params}`;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
    return;
  }
  window.prompt(t("copyLink"), url);
}
```

For mobile, pass an `actions` prop from `App` that copies the current viewport center using a callback exposed by `MapView` or a shared `lastViewport` state.

- [ ] **Step 5: Verify anchors/restrictions/actions**

Run:

```bash
cd frontend
npm run build
```

Manual check:

- Anchor toggle hides/shows anchors.
- Below anchor zoom threshold, status says to zoom in.
- Detailed anchor wedges appear for small counts.
- Restriction toggles load overlays and descriptions.
- Desktop right-click popup opens Google Maps and copies link.
- Mobile sheet includes map actions.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: port anchors restrictions and map actions"
```

---

### Task 9: Production Static Serving, Justfile, Docker, And CI

**Files:**
- Modify: `highliner/app.py`
- Modify: `justfile`
- Modify: `Dockerfile`
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_static_frontend.py`

**Interfaces:**
- Consumes: `frontend/dist/index.html` production build.
- Produces: FastAPI serves React build from `/`; Docker image includes built frontend; CI verifies frontend.

- [ ] **Step 1: Add static-serving backend test**

Create `tests/test_static_frontend.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from highliner.app import create_app


def test_serves_react_dist_when_present(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    dist = project_root / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div>react build</div>")
    monkeypatch.setattr("highliner.app.PROJECT_ROOT", project_root)

    app = create_app(data_dir=tmp_path / "data")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "react build" in response.text
    assert response.headers["Cache-Control"] == "no-cache"
```

- [ ] **Step 2: Modify FastAPI static mount**

Modify `highliner/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from highliner.core import config
from highliner.router import (anchors, density, regions, restrictions, zones)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    react_dist = PROJECT_ROOT / "frontend" / "dist"
    legacy_web = PROJECT_ROOT / "web"
    static_dir = react_dist if (react_dist / "index.html").exists() else legacy_web
    if static_dir.exists():
        app.mount("/", _NoCacheStaticFiles(directory=static_dir, html=True), name="web")

    return app


app = create_app()
```

- [ ] **Step 3: Update justfile**

Append to `justfile`:

```make
# Install frontend dependencies.
frontend-install:
    cd frontend && npm install

# Vite dev server. Run alongside `just dev`.
frontend-dev:
    cd frontend && npm run dev

# Build the React frontend for FastAPI/Docker static serving.
frontend-build:
    cd frontend && npm run build

# Run frontend tests.
frontend-test:
    cd frontend && npm test

# Run backend and frontend checks.
check:
    just typecheck
    just test
    just frontend-test
    just frontend-build
```

- [ ] **Step 4: Update Dockerfile**

Modify `Dockerfile` into three stages:

```dockerfile
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY highliner ./highliner
COPY web ./web

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "highliner.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Update CI**

Modify `.github/workflows/ci.yml` check job, adding Node before backend checks or after Python setup:

```yaml
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        run: npm ci
        working-directory: frontend

      - name: Test frontend
        run: npm test
        working-directory: frontend

      - name: Build frontend
        run: npm run build
        working-directory: frontend
```

- [ ] **Step 6: Verify serving and CI commands locally**

Run:

```bash
just frontend-test
just frontend-build
uv run pytest tests/test_static_frontend.py -v
just test
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add highliner/app.py justfile Dockerfile .github/workflows/ci.yml tests/test_static_frontend.py
git commit -m "feat: serve react frontend build"
```

---

### Task 10: Final Parity Pass And Legacy Cleanup

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Optional delete after verification: `web/index.html`, `web/app.js`, `web/i18n.js`, `web/style.css`, `web/analytics.js`

**Interfaces:**
- Consumes: completed React app and production static serving.
- Produces: documented frontend workflow and final verified parity.

- [ ] **Step 1: Update docs**

Update `README.md` setup section with:

```markdown
### Frontend development

The production frontend is a Vite React app in `frontend/`.

Run the API:

    just dev

Run the frontend in another shell:

    just frontend-dev

Build/test frontend:

    just frontend-test
    just frontend-build
```

Update `AGENTS.md` frontend section to replace the no-build `web/` note with:

```markdown
## Frontend

The frontend lives in `frontend/` and is a Vite React TypeScript app using
Tailwind and shadcn-style component source. FastAPI serves `frontend/dist` in
production. During development, run `just dev` for the API and
`just frontend-dev` for Vite.
```

- [ ] **Step 2: Run full verification**

Run:

```bash
just check
docker build -t highliner-frontend-check .
```

Expected: typecheck, backend tests, frontend tests, frontend build, and Docker build all pass.

- [ ] **Step 3: Manual browser parity checklist**

Run:

```bash
just dev
cd frontend && npm run dev
```

Check:

- Desktop sidebar appears, collapses, and map resizes.
- Mobile viewport shows bottom peek card and expandable bottom sheet.
- Disclaimer appears every reload and language can be switched before accepting.
- Region select fits the map to bounds.
- URL `?lat=41.6&lng=1.83&z=13` initializes the map at that view.
- Zoom `<= 12` shows density cells and legend/status.
- Zoom `> 12` shows zones.
- Panning accumulates zones without duplicates.
- Slider commit resets accumulated zones.
- Anchor toggle works; low zoom shows zoom-in status; high zoom shows anchors.
- Restrictions toggle descriptions and map overlays.
- Desktop right-click menu has Google Maps and copy link.
- Mobile bottom sheet exposes map actions.
- Catalan, Spanish, and English switch static controls, statuses, and popups.

- [ ] **Step 4: Remove legacy web only after parity passes**

If every item in Step 3 passes, delete:

```bash
rm web/index.html web/app.js web/i18n.js web/style.css web/analytics.js
rmdir web
```

If any item fails, keep `web/` and create follow-up fixes before deleting it.

- [ ] **Step 5: Commit docs and cleanup**

If `web/` is deleted:

```bash
git add README.md AGENTS.md web
git commit -m "docs: document react frontend workflow"
```

If `web/` is kept:

```bash
git add README.md AGENTS.md
git commit -m "docs: document react frontend workflow"
```

---

## Self-Review Notes

- Spec coverage: Tasks cover tooling, shadcn/Tailwind, i18n, API clients, shell, desktop sidebar, mobile sheet, Leaflet map, density/zones, anchors, restrictions, share links, disclaimer, static serving, Docker, CI, docs, and final parity cleanup.
- Red-flag scan: The plan contains no unresolved steps. Any implementation worker should replace the plan snippets only when the generated shadcn component source differs from installed package APIs.
- Type consistency: The plan uses `Region`, `ZoneFeatureCollection`, `DensityFeatureCollection`, `AnchorFeatureCollection`, `RestrictionLayerMeta`, and `RestrictionFeatureCollection` from `frontend/src/types/highliner.ts`; helper and component signatures reference those names consistently.
