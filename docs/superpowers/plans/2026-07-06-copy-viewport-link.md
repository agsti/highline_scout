# Copy Viewport Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Copy link" item to the right-click map menu that copies a URL encoding the clicked point + zoom, and make the app open at that view when such a URL is loaded.

**Architecture:** The existing `contextmenu` handler in `web/app.js` currently opens a Leaflet popup containing a single `<a>` ("View in Google Maps"). It becomes a small popup menu built as DOM nodes (so a click handler can run JS, not just navigate), with a second `<button>` that writes `?lat=&lng=&z=` to the clipboard via `navigator.clipboard`, falling back to `prompt()` if that API is unavailable or rejects. Separately, before the map is constructed, `app.js` checks `location.search` for those same three params and uses them as the initial view instead of the hardcoded Montserrat default.

**Tech Stack:** Vanilla JS, Leaflet 1.9.4, no build step, no test framework for the frontend (this repo's JS has none — verification is manual via `just dev`, matching the pattern in `docs/superpowers/plans/2026-07-03-zoomed-out-density.md` Task 5).

## Global Constraints

- No new dependencies — Leaflet and vanilla JS/DOM APIs only.
- Every new user-facing string needs `ca`/`es`/`en` entries in `web/i18n.js`'s `STRINGS`, keeping all three catalogs' key sets identical (enforced by the existing `assertCatalogParity` dev check).
- `lat`/`lng` in the copied URL are rounded to 5 decimals (~1m precision).
- Query param names are `lat`, `lng`, `z` (matches the existing `z` convention used elsewhere in `app.js`, e.g. the `/density` and `/zones` fetches).

---

### Task 1: i18n keys for the copy-link menu item and confirmation

**Files:**
- Modify: `web/i18n.js:61-62` (ca), `web/i18n.js:108-109` (es), `web/i18n.js:155-156` (en)

**Interfaces:**
- Consumes: nothing new.
- Produces: `t("copyLink")` and `t("linkCopied")`, consumed by Task 3.

- [ ] **Step 1: Add the two keys to each language block**

In `web/i18n.js`, the `ca` block currently ends with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "Veure a Google Maps",
  },
```

Replace with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "Veure a Google Maps",
    copyLink: "Copia l'enllaç",
    linkCopied: "Enllaç copiat",
  },
```

The `es` block currently ends with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "Ver en Google Maps",
  },
```

Replace with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "Ver en Google Maps",
    copyLink: "Copiar enlace",
    linkCopied: "Enlace copiado",
  },
```

The `en` block currently ends with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "View in Google Maps",
  },
};
```

Replace with:

```javascript
    // --- right-click map menu ---
    viewInGoogleMaps: "View in Google Maps",
    copyLink: "Copy link",
    linkCopied: "Link copied",
  },
};
```

- [ ] **Step 2: Verify catalog parity**

Run: `just dev`, then open `http://127.0.0.1:8000` and check the browser console.
Expected: no `i18n: catalog "..." key set differs from "ca"` warning. (The `assertCatalogParity` check in `i18n.js` runs on load and logs a warning if any catalog's keys diverge — since all three blocks gained the same two keys, there should be no warning.)

- [ ] **Step 3: Commit**

```bash
git add web/i18n.js
git commit -m "i18n: add copy-link menu item and confirmation strings"
```

---

### Task 2: Load initial viewport from URL if present

**Files:**
- Modify: `web/app.js:1`

**Interfaces:**
- Consumes: nothing new (uses global `window.location`, `URLSearchParams`).
- Produces: `map` (existing global, now possibly initialized at a URL-supplied view instead of the hardcoded default). No new exports — Task 3 does not depend on this task.

- [ ] **Step 1: Replace the hardcoded `setView` with a URL-aware initial view**

In `web/app.js`, the file currently starts with:

```javascript
const map = L.map("map").setView([41.6, 1.83], 13); // Montserrat area
```

Replace with:

```javascript
// If the URL carries a viewport (from a copied "Copy link"), start there
// instead of the hardcoded default. All three params must be present and
// parse to finite numbers, or we fall back to the default view.
function initialViewFromURL() {
  const params = new URLSearchParams(window.location.search);
  const lat = parseFloat(params.get("lat"));
  const lng = parseFloat(params.get("lng"));
  const z = parseFloat(params.get("z"));
  if (Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(z)) {
    return { center: [lat, lng], zoom: z };
  }
  return null;
}

const initialView = initialViewFromURL() || { center: [41.6, 1.83], zoom: 13 }; // Montserrat area
const map = L.map("map").setView(initialView.center, initialView.zoom);
```

- [ ] **Step 2: Verify in the browser**

Run: `just dev`. Load each of:
- `http://127.0.0.1:8000` — expect the default Montserrat view (zoom 13, centered ~41.6, 1.83).
- `http://127.0.0.1:8000/?lat=41.5&lng=2.0&z=15` — expect the map to open centered at (41.5, 2.0) at zoom 15.
- `http://127.0.0.1:8000/?lat=foo&lng=2.0&z=15` — expect the default Montserrat view (invalid `lat` falls back).

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: open the map at a URL-supplied viewport when present"
```

---

### Task 3: Copy-link menu item on right-click

**Files:**
- Modify: `web/app.js:195-205` (the existing `contextmenu` handler)
- Modify: `web/style.css` (add menu layout rule)

**Interfaces:**
- Consumes: `t("viewInGoogleMaps")`, `t("copyLink")`, `t("linkCopied")` (Task 1); existing globals `map`, `$`.
- Produces: nothing consumed elsewhere — this is the terminal task.

- [ ] **Step 1: Replace the contextmenu handler with a 2-item DOM menu**

In `web/app.js`, replace:

```javascript
// Right-click anywhere on the map: offer a link to the exact same point on
// Google Maps. Leaflet's "contextmenu" event already suppresses the browser's
// native right-click menu and reports the clicked coordinate as e.latlng.
map.on("contextmenu", (e) => {
  const { lat, lng } = e.latlng;
  const url = `https://www.google.com/maps?q=${lat},${lng}`;
  L.popup()
    .setLatLng(e.latlng)
    .setContent(`<a href="${url}" target="_blank" rel="noopener">${t("viewInGoogleMaps")}</a>`)
    .openOn(map);
});
```

with:

```javascript
// Right-click anywhere on the map: offer a small menu for the clicked point —
// open it in Google Maps, or copy a link that reopens this app at the same
// point and zoom. Leaflet's "contextmenu" event already suppresses the
// browser's native right-click menu and reports the clicked coordinate as
// e.latlng.
map.on("contextmenu", (e) => {
  const { lat, lng } = e.latlng;
  const zoom = map.getZoom();
  L.popup().setLatLng(e.latlng).setContent(buildMapContextMenu(lat, lng, zoom)).openOn(map);
});

// Build the right-click popup's content: a link to view the point in Google
// Maps, and a button that copies a link back into this app at the same point.
function buildMapContextMenu(lat, lng, zoom) {
  const menu = document.createElement("div");
  menu.className = "map-context-menu";

  const gmapsLink = document.createElement("a");
  gmapsLink.href = `https://www.google.com/maps?q=${lat},${lng}`;
  gmapsLink.target = "_blank";
  gmapsLink.rel = "noopener";
  gmapsLink.textContent = t("viewInGoogleMaps");
  menu.appendChild(gmapsLink);

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.textContent = t("copyLink");
  copyBtn.addEventListener("click", () => copyViewportLink(lat, lng, zoom));
  menu.appendChild(copyBtn);

  return menu;
}

// Build a URL that reopens this app at (lat, lng, zoom), copy it to the
// clipboard, and confirm via #status. Falls back to prompt() with the URL if
// the Clipboard API is unavailable or the write is rejected (e.g. permission
// denied, insecure context).
function copyViewportLink(lat, lng, zoom) {
  const params = new URLSearchParams({
    lat: lat.toFixed(5),
    lng: lng.toFixed(5),
    z: zoom,
  });
  const url = `${window.location.origin}${window.location.pathname}?${params}`;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(
      () => { map.closePopup(); flashStatus(t("linkCopied")); },
      () => { window.prompt(t("copyLink"), url); },
    );
  } else {
    window.prompt(t("copyLink"), url);
  }
}

// Temporarily overwrite #status's text with `message`, restoring whatever
// text was there before after `ms` milliseconds.
function flashStatus(message, ms = 2000) {
  const el = $("status");
  const prev = el.textContent;
  el.textContent = message;
  setTimeout(() => { el.textContent = prev; }, ms);
}
```

- [ ] **Step 2: Add a layout rule for the menu**

In `web/style.css`, append:

```css
/* --- Right-click map context menu (Leaflet popup content) --- */
.map-context-menu { display: flex; flex-direction: column; gap: 6px; min-width: 140px; }
.map-context-menu a, .map-context-menu button {
  font: inherit; text-align: left; background: none; border: none; padding: 2px 0;
  color: #1f9e8f; cursor: pointer; text-decoration: none;
}
.map-context-menu a:hover, .map-context-menu button:hover { text-decoration: underline; }
```

- [ ] **Step 3: Verify in the browser**

Run: `just dev`, open `http://127.0.0.1:8000`.
- Right-click anywhere on the map: expect a popup with two stacked items, "View in Google Maps" and "Copy link".
- Click "View in Google Maps": expect a new tab opening Google Maps centered on the clicked point.
- Right-click again, click "Copy link": expect the popup to close and `#status` to briefly read "Link copied" (ca: "Enllaç copiat", es: "Enlace copiado") before reverting. Paste the clipboard contents into the address bar of a new tab — expect the map to reopen centered on the originally clicked point at the same zoom.
- Repeat the copy in all three languages (use the language flags in the panel) and confirm both menu item labels and the confirmation text are translated.
- To exercise the fallback path: open devtools → Application/Permissions and block clipboard-write for the page (or open the page over `http://` on a non-localhost host, where the Clipboard API is unavailable), then click "Copy link" again — expect a `prompt()` dialog pre-filled with the URL instead of a silent failure.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat: add copy-link item to the right-click map menu"
```
