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

const urlView = initialViewFromURL();
const initialView = urlView || { center: [41.6, 1.83], zoom: 13 }; // Montserrat area
const map = L.map("map").setView(initialView.center, initialView.zoom);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);

// Sequential single-hue teal ramp, light -> dark. t in [0,1]. Shared by the
// zone fills (below) and the zoomed-out density cells so the whole map speaks
// one color language: more teal means more/taller highline potential.
function tealShade(t) {
  const h = 168 + 16 * t;   // 168 -> 184
  const s = 45 + 25 * t;    // 45% -> 70%
  const l = 88 - 62 * t;    // 88% -> 26%
  return `hsl(${h}, ${s}%, ${l}%)`;
}

// Every zone is drawn in the same dark cyan, regardless of its properties.
const ZONE_COLOR = "hsl(184, 70%, 26%)";

const layer = L.geoJSON(null, {
  style: () => ({
    color: ZONE_COLOR,
    weight: 2,
    fillOpacity: 0.35,
  }),
  onEachFeature: (f, l) => l.bindPopup(zonePopupHTML(f.properties)),
}).addTo(map);

// Popup/tooltip text for a zone. Kept separate from onEachFeature so a language
// switch can re-render it in place (see retranslateMap) without re-fetching.
function zonePopupHTML(p) {
  return t("zonePopup", {
    min: p.height_min, max: p.height_max,
    lmin: Math.round(p.length_min), lmax: Math.round(p.length_max),
    na: p.n_anchors, np: p.n_pairs,
  });
}

// Zoomed-out density pyramid. At/below this zoom the viewport is too large for
// per-pair zones, so we show precomputed hotspot cells shaded by pair count.
const DENSITY_MAX_ZOOM = 12;   // show density at/below this Leaflet zoom, zones above
// Request a tile layer finer than the display zoom so hotspot cells are smaller.
// Mirrors config.DENSITY_ZOOM_OFFSET; DENSITY_TILE_MIN/MAX bracket the precomputed
// pyramid (config.DENSITY_ZOOM_LEVELS) and clamp the requested layer.
const DENSITY_ZOOM_OFFSET = 2;
const DENSITY_TILE_MIN = 6;
const DENSITY_TILE_MAX = 14;
// Cell shading is *rank-based*: each cell is colored by where its pair count
// ranks among the cells currently in view, not by the absolute count. Counts
// span ~6 orders of magnitude and their range shifts with zoom, so any fixed
// linear cutoff pins almost everything to one end of the ramp. Ranking spreads
// the ramp evenly across whatever is on screen. Sparse -> pale mint, dense ->
// deep teal (the anchor hue): more shading means more highline potential.
let densitySorted = []; // ascending pair counts of the cells currently shown

// Fraction in [0,1] giving n's rank within the current cell set (0 = sparsest,
// 1 = densest). Ties share their averaged rank.
function densityRank(n) {
  const m = densitySorted.length;
  if (m <= 1) return 1;
  let lo = 0, hi = m;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (densitySorted[mid] < n) lo = mid + 1; else hi = mid; }
  let hiIdx = lo;
  while (hiIdx < m && densitySorted[hiIdx] === n) hiIdx++;
  return ((lo + hiIdx - 1) / 2) / (m - 1);
}

const densityLayer = L.geoJSON(null, {
  style: (f) => {
    const t = densityRank(f.properties.n_pairs);
    return {
      color: tealShade(Math.min(t + 0.15, 1)), // stroke a shade darker than fill
      weight: 0.5,
      fillColor: tealShade(t),
      fillOpacity: 0.2 + 0.55 * t,   // sparse cells fade back, dense ones read solid
    };
  },
  onEachFeature: (f, l) => l.bindTooltip(densityTooltipHTML(f.properties)),
}).addTo(map);

function densityTooltipHTML(p) {
  // length_min/max are absent (null) in density layers built before length tracking.
  const lenHint = p.length_min == null ? ""
    : t("densityLenHint", { min: Math.round(p.length_min), max: Math.round(p.length_max) });
  return t("densityTooltip", { n: p.n_pairs, max: Math.round(p.max_exposure), lenHint });
}

// Relative-density key, shown only while the density layer is active.
const densityLegend = L.control({ position: "bottomright" });
densityLegend.onAdd = () => {
  const div = L.DomUtil.create("div", "density-legend");
  const bar = [0, 0.25, 0.5, 0.75, 1]
    .map((t) => `<span style="background:${tealShade(t)}"></span>`).join("");
  div.innerHTML = `<div class="dl-title">${t("lineDensity")}</div>`
    + `<div class="dl-bar">${bar}</div>`
    + `<div class="dl-ends"><span>${t("sparse")}</span><span>${t("dense")}</span></div>`;
  return div;
};
let densityLegendShown = false;
function showDensityLegend(on) {
  if (on === densityLegendShown) return;
  if (on) densityLegend.addTo(map); else densityLegend.remove();
  densityLegendShown = on;
}

const ANCHOR_COLOR = "#1f9e8f";
// Below this zoom the viewport covers so much terrain that /anchors would
// exceed the server's MAX_ANCHORS_IN_VIEW cap and 413. Skip the request
// entirely and prompt the user to zoom in.
const ANCHOR_MIN_ZOOM = 12;
const ANCHOR_DETAIL_LIMIT = 400; // above this, draw dots instead of wedges
const ANCHOR_WEDGE_RADIUS_M = 30;
const anchorCanvas = L.canvas({ padding: 0.5 });
const anchorLayer = L.layerGroup().addTo(map);

// Destination point given start lat/lon, bearing (deg clockwise from north),
// and distance in meters. Matches highliner.geo.bearing's convention.
function destPoint(lat, lon, bearingDeg, distM) {
  const R = 6371000;
  const d = distM / R;
  const brng = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
  const lon2 = lon1 + Math.atan2(
    Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
    Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

// Polygon ring for a sector wedge: apex at center, arc swept clockwise
// from `start` to `end` bearing at a fixed radius.
function wedge(lat, lon, start, end) {
  let span = (end - start) % 360;
  if (span <= 0) span += 360;
  const steps = Math.max(2, Math.ceil(span / 10));
  const pts = [[lat, lon]];
  for (let i = 0; i <= steps; i++) {
    pts.push(destPoint(lat, lon, start + (span * i) / steps, ANCHOR_WEDGE_RADIUS_M));
  }
  return pts;
}

const $ = (id) => document.getElementById(id);

// Status lines (zone/anchor/restriction counts, prompts, errors) are the one
// piece of on-screen text a fetch leaves behind. Remember each element's latest
// render as a thunk so a language switch can replay it — re-translated via t()
// in the new LANG — without re-fetching. Keyed by element, so the newest render
// per line wins (its resting state).
const statusRenderers = new Map();
function setStatus(el, thunk) {
  statusRenderers.set(el, thunk);
  el.textContent = thunk();
}
function replayStatuses() {
  statusRenderers.forEach((thunk, el) => { el.textContent = thunk(); });
}

// Show/hide the map spinner while zones or density hotspots are being computed.
function setLoading(on) {
  $("spinner").hidden = !on;
}

// Fetch a GeoJSON FeatureCollection, writing user-facing status to `statusEl`.
// Returns the parsed FeatureCollection, or null when the request hit the
// viewport cap (413) or otherwise errored — so callers must skip rendering on
// null instead of assuming a `.features` array.
async function fetchFC(url, statusEl, nounKey) {
  const res = await fetch(url);
  if (res.status === 413) {
    statusEl.textContent = t("zoomInToSee", { noun: t(nounKey) });
    return null;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    statusEl.textContent = t("error", { detail: body.detail || res.status });
    return null;
  }
  return res.json();
}

// The pairing sliders are the "range inputs": changing one invalidates every
// zone on the map (they were computed under different parameters), so it wipes
// the accumulated set and starts fresh. Panning/zooming, by contrast, keeps
// what's there and only adds the new viewport's zones (see refresh()).
const ctrls = ["maxLen", "minExp"];
// `input` fires continuously while dragging (keep the label live); `change`
// fires once on release, so that's where the network refresh() goes.
ctrls.forEach((id) => {
  $(id).addEventListener("input", () => { $(id + "V").textContent = $(id).value; });
  $(id).addEventListener("change", () => refresh({ reset: true }));
});
map.on("moveend", () => refresh());

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

const regionBounds = {}; // region name -> [w, s, e, n] in lon/lat

// Fly the map to a region's extent. fitBounds fires `moveend`, which already
// triggers refresh()/refreshAnchors(); fall back to an in-place refresh only
// when the region has no known bounds.
function flyToRegion(name) {
  const b = regionBounds[name];
  if (!b) { refresh(); refreshAnchors(); return; }
  map.fitBounds([[b[1], b[0]], [b[3], b[2]]]);
}

async function fetchRegions() {
  const r = await fetch("/regions").then((x) => x.json());
  r.regions.forEach((reg) => { regionBounds[reg.name] = reg.bounds_lonlat; });
  return r.regions;
}

async function loadRegions() {
  const regions = await fetchRegions();
  regions.forEach((reg) => {
    const o = document.createElement("option");
    o.value = o.textContent = reg.name;
    $("region").appendChild(o);
  });
  // Switching region is a context switch, not a range change: drop the other
  // region's accumulated zones before flying so they don't linger on the map.
  $("region").addEventListener("change", () => {
    clearZones();
    flyToRegion($("region").value);
  });
  if (urlView) { refresh(); refreshAnchors(); }
  else if ($("region").value) flyToRegion($("region").value);
  else { refresh(); refreshAnchors(); }
}

async function refreshDensity() {
  const region = $("region").value;
  const z = Math.min(Math.max(Math.round(map.getZoom()) + DENSITY_ZOOM_OFFSET,
                              DENSITY_TILE_MIN), DENSITY_TILE_MAX);
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const params = new URLSearchParams({ region, z, bbox_lonlat: bbox });
  $("status").textContent = t("loadingHotspots");
  setLoading(true);
  try {
    const fc = await fetchFC("/density?" + params, $("status"), "nounHotspots");
    densityLayer.clearLayers();
    if (!fc) return;
    // Rank each cell against the set now in view (styling reads densitySorted).
    densitySorted = fc.features.map((ft) => ft.properties.n_pairs).sort((a, b) => a - b);
    densityLayer.addData(fc);
    showDensityLegend(fc.features.length > 0);
    $("status").textContent = t("hotspotCells", { n: fc.features.length });
  } catch (e) {
    $("status").textContent = t("error", { detail: e });
  } finally {
    setLoading(false);
  }
}

// Zones accumulate across pans and zooms instead of being cleared on every
// move, so a scout can range over the terrain and keep every zone found so far
// on screen. Only a change to the range inputs, a region switch, or dropping to
// the density view wipes the set (see clearZones callers).
//
// Zones carry no stable id — each is just a cluster of the anchors that fell in
// the requested viewport — so overlapping viewports recompute the same cliff.
// We dedupe by centroid snapped to a ~50 m grid so pans don't stack duplicate
// polygons on top of each other.
const ZONE_DEDUP_GRID_DEG = 0.0005; // ~50 m; centroid quantum for zone identity
const shownZoneKeys = new Set();

function zoneKey(feature) {
  const ring = feature.geometry.coordinates[0];
  let lon = 0, lat = 0;
  for (const [x, y] of ring) { lon += x; lat += y; }
  lon /= ring.length;
  lat /= ring.length;
  return `${Math.round(lat / ZONE_DEDUP_GRID_DEG)}:${Math.round(lon / ZONE_DEDUP_GRID_DEG)}`;
}

function clearZones() {
  layer.clearLayers();
  shownZoneKeys.clear();
}

async function refresh({ reset = false } = {}) {
  const region = $("region").value;
  if (!region) return;
  if (map.getZoom() <= DENSITY_MAX_ZOOM) {
    clearZones();
    return refreshDensity();
  }
  densityLayer.clearLayers();
  showDensityLegend(false);
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const params = new URLSearchParams({
    region,
    bbox_lonlat: bbox,
    max_len: $("maxLen").value,
    min_exposure: $("minExp").value,
  });
  $("status").textContent = t("searching");
  setLoading(true);
  try {
    const fc = await fetchFC("/zones?" + params, $("status"), "nounZones");
    if (reset) clearZones();
    if (!fc) return;
    // Keep only zones not already on the map, so overlapping viewports don't
    // stack duplicates as the user pans.
    const fresh = fc.features.filter((ft) => {
      const k = zoneKey(ft);
      if (shownZoneKeys.has(k)) return false;
      shownZoneKeys.add(k);
      return true;
    });
    layer.addData({ type: "FeatureCollection", features: fresh });
    $("status").textContent = t("zonesCount", { n: shownZoneKeys.size });
  } catch (e) {
    $("status").textContent = t("error", { detail: e });
  } finally {
    setLoading(false);
  }
}

function anchorPopup(p) {
  const secs = p.sectors
    .map((s) => t("anchorSector", {
      a: Math.round(s[0]), b: Math.round(s[1]), drop: Math.round(s[2]),
    }))
    .join("<br>");
  return t("anchorPopup", { elev: Math.round(p.elev), sectors: secs });
}

function renderAnchors(fc) {
  anchorLayer.clearLayers();
  const detailed = fc.features.length <= ANCHOR_DETAIL_LIMIT;
  fc.features.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    if (detailed) {
      p.sectors.forEach((s) => {
        L.polygon(wedge(lat, lon, s[0], s[1]), {
          color: ANCHOR_COLOR, weight: 1, fillOpacity: 0.25,
        }).addTo(anchorLayer);
      });
      L.circleMarker([lat, lon], {
        radius: 4, color: ANCHOR_COLOR, weight: 1, fillOpacity: 1,
      }).bindPopup(anchorPopup(p)).addTo(anchorLayer);
    } else {
      L.circleMarker([lat, lon], {
        renderer: anchorCanvas, radius: 2, color: ANCHOR_COLOR,
        weight: 1, fillOpacity: 0.8,
      }).bindPopup(anchorPopup(p)).addTo(anchorLayer);
    }
  });
}

async function refreshAnchors() {
  if (!$("showAnchors").checked) {
    anchorLayer.clearLayers();
    $("anchorStatus").textContent = "";
    return;
  }
  const region = $("region").value;
  if (!region) return;
  if (map.getZoom() < ANCHOR_MIN_ZOOM) {
    anchorLayer.clearLayers();
    $("anchorStatus").textContent = t("zoomInToSee", { noun: t("nounAnchors") });
    return;
  }
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  try {
    const url = "/anchors?" + new URLSearchParams({ region, bbox_lonlat: bbox });
    const fc = await fetchFC(url, $("anchorStatus"), "nounAnchors");
    if (!fc) {
      anchorLayer.clearLayers();
      return;
    }
    renderAnchors(fc);
    $("anchorStatus").textContent = t("anchorsCount", { n: fc.features.length });
  } catch (e) {
    anchorLayer.clearLayers();
    $("anchorStatus").textContent = t("anchorError", { detail: e });
  }
}

map.on("moveend", refreshAnchors);
$("showAnchors").addEventListener("change", refreshAnchors);

// --- protected-area (restriction) overlays ---------------------------------
// Drawn in a dedicated pane below the zone polygons and anchor markers so the
// markers stay clickable on top. Layers are independent of the selected region.
map.createPane("restrictions");
map.getPane("restrictions").style.zIndex = 350;
const restrictionColor = {}; // layer id -> hex color
const restrictionLabel = {}; // layer id -> display label (current language)
const restrictionServer = {}; // layer id -> server {label,tooltip,highlight} (Catalan fallback)

const restrictionLayer = L.geoJSON(null, {
  pane: "restrictions",
  style: (f) => ({
    color: restrictionColor[f.properties.layer] || "#888",
    weight: 1, fillOpacity: 0.15,
  }),
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindPopup(`<b>${restrictionLabel[p.layer] || p.layer}</b>`
      + (p.name ? `<br>${p.name}` : ""));
  },
}).addTo(map);

function enabledRestrictions() {
  return [...document.querySelectorAll("#restrictionLayers input:checked")]
    .map((c) => c.dataset.layer);
}

async function refreshRestrictions() {
  const ids = enabledRestrictions();
  if (!ids.length) {
    restrictionLayer.clearLayers();
    $("restrictionStatus").textContent = "";
    return;
  }
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const url = "/restrictions?" + new URLSearchParams(
    { bbox_lonlat: bbox, layers: ids.join(",") });
  try {
    const fc = await fetchFC(url, $("restrictionStatus"), "nounProtectedAreas");
    restrictionLayer.clearLayers();
    if (!fc) return;
    restrictionLayer.addData(fc);
    $("restrictionStatus").textContent = t("protectedAreasCount", { n: fc.features.length });
  } catch (e) {
    restrictionLayer.clearLayers();
    $("restrictionStatus").textContent = t("error", { detail: e });
  }
}

// Append `text` to `desc`, wrapping `highlight` (a verbatim substring) in a
// <mark> so the highliner-relevant part stands out. Uses text nodes, so the
// description is never interpreted as HTML.
function appendDescText(desc, text, highlight) {
  const i = highlight ? text.indexOf(highlight) : -1;
  if (i < 0) { desc.append(text); return; }
  if (i > 0) desc.append(text.slice(0, i));
  const mark = document.createElement("mark");
  mark.textContent = highlight;
  desc.append(mark);
  desc.append(text.slice(i + highlight.length));
}

async function loadRestrictionLayers() {
  const r = await fetch("/restrictions/layers").then((x) => x.json());
  const box = $("restrictionLayers");
  r.layers.forEach((rl) => {
    restrictionColor[rl.id] = rl.color;
    // Keep the server's Catalan text as the fallback, then resolve the label /
    // tooltip / highlight for the active language.
    restrictionServer[rl.id] = {
      label: rl.label, tooltip: rl.tooltip, highlight: rl.highlight };
    const tx = restrictionText(rl.id, restrictionServer[rl.id]);
    restrictionLabel[rl.id] = tx.label;
    const row = document.createElement("div");
    row.className = "restriction-row";
    row.dataset.layer = rl.id;
    const label = document.createElement("label");
    label.className = "restriction";
    // Label text lives in its own span (set via textContent) so it can be
    // re-translated in place on a language switch — see applyRestrictionI18n.
    label.innerHTML = `<input type="checkbox" data-layer="${rl.id}" /> `
      + `<span class="swatch" style="background:${rl.color}"></span> `
      + `<span class="restr-label"></span>`;
    label.querySelector(".restr-label").textContent = tx.label || "";
    // The description sits inline under the toggle, shown only while the layer
    // is enabled, with the highliner-relevant clause highlighted.
    const desc = document.createElement("p");
    desc.className = "restriction-desc";
    appendDescText(desc, tx.tooltip || "", tx.highlight);
    desc.hidden = true;
    const cb = label.querySelector("input");
    cb.addEventListener("change", () => {
      desc.hidden = !cb.checked;
      refreshRestrictions();
    });
    row.append(label, desc);
    box.appendChild(row);
  });
}

// Re-translate the restriction panel rows in place for the active language,
// preserving each checkbox and whether its description is shown. Map popups
// pick up the new label via restrictionLabel when refreshRestrictions runs.
function applyRestrictionI18n() {
  document.querySelectorAll("#restrictionLayers .restriction-row").forEach((row) => {
    const id = row.dataset.layer;
    const tx = restrictionText(id, restrictionServer[id]);
    restrictionLabel[id] = tx.label;
    const lbl = row.querySelector(".restr-label");
    if (lbl) lbl.textContent = tx.label || "";
    const desc = row.querySelector(".restriction-desc");
    if (desc) {
      desc.textContent = "";
      appendDescText(desc, tx.tooltip || "", tx.highlight);
    }
  });
}

map.on("moveend", refreshRestrictions);
loadRestrictionLayers();

// Language switcher — flag buttons at the foot of the panel. i18n.js already
// resolved the initial LANG (remembered choice / browser / Catalan); mark it
// active, then on click swap the language and re-render everything: static
// labels plus the dynamic layers whose popups, tooltips, status line and
// density legend are built via t().
// Mirror the sidebar's flag switcher into the disclaimer modal so a user can
// pick their language before reading (and dismissing) the warning. Clone the
// existing group — one markup source — and suffix the flag SVGs' internal ids
// so the copy stays valid (duplicate ids would break the clip-path reference).
// The modal shows only the current language's flag (see .modal-lang CSS); a
// caret hints that clicking it reveals the others.
(function mirrorLangFlagsIntoModal() {
  const slot = $("modalLang");
  if (!slot) return;
  const clone = $("langFlags").cloneNode(true);
  clone.querySelectorAll("[id]").forEach((el) => { el.id += "-m"; });
  clone.querySelectorAll("[clip-path]").forEach((el) => {
    el.setAttribute("clip-path",
      el.getAttribute("clip-path").replace(/\)$/, "-m)"));
  });
  while (clone.firstChild) slot.appendChild(clone.firstChild);
  const caret = document.createElement("span");
  caret.className = "modal-lang-caret";
  caret.textContent = "▾";
  caret.setAttribute("aria-hidden", "true");
  slot.appendChild(caret);
  // Collapsed, only the active flag is clickable: the first click expands the
  // group (swallowed so it doesn't re-select the current language); once open,
  // clicking any flag switches language (per-flag handler below) and collapses.
  slot.addEventListener("click", (e) => {
    if (!e.target.closest(".flag")) return;
    if (slot.classList.contains("open")) {
      slot.classList.remove("open");
    } else {
      e.stopImmediatePropagation();
      slot.classList.add("open");
    }
  }, true);
})();

// Every flag button, in the sidebar and in the modal, drives the same switch.
const langFlags = document.querySelectorAll(".flag");
function markActiveLang() {
  langFlags.forEach((b) => {
    const on = b.dataset.lang === LANG;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}
markActiveLang();
langFlags.forEach((b) => {
  b.addEventListener("click", () => {
    if (b.dataset.lang === LANG) return;
    setLang(b.dataset.lang);
    markActiveLang();
    applyStaticI18n();
    // The density legend's text is baked in by its onAdd, which only runs on
    // add — drop it so refresh() re-adds (and re-translates) it in the new
    // language. refresh() rebuilds the status line, popups and tooltips.
    showDensityLegend(false);
    applyRestrictionI18n();
    refresh();
    refreshAnchors();
    refreshRestrictions();
  });
});

// Safety disclaimer — shown over the whole app on every load. Finding and
// judging a spot is the most dangerous part of highlining, so the user must
// acknowledge that the tool only suggests terrain and carries no liability
// before scouting. Dismissed (not remembered) on "I understand".
$("disclaimerAccept").addEventListener("click", () => {
  $("disclaimer").hidden = true;
});
$("disclaimerAccept").focus();

// --- Panel minimize / expand and mobile auto-hide ---
const panel = document.getElementById("panel");
const panelToggle = document.getElementById("panelToggle");
const panelBackdrop = document.getElementById("panelBackdrop");

function isMobile() { return window.innerWidth <= 768; }

function isPanelOpen() {
  return isMobile() ? panel.classList.contains("open") : !panel.classList.contains("collapsed");
}

// Debounce: call invalidateSize after CSS transition finishes (250ms)
function scheduleInvalidate() {
  clearTimeout(panelTimer);
  panelTimer = setTimeout(() => map.invalidateSize(), 300);
}
let panelTimer;

// Position the floating toggle button when panel opens/closes
function updateTogglePosition() {
  const mobile = isMobile();
  const open = isPanelOpen();
  const mw = Math.min(300, window.innerWidth * 0.85);
  if (mobile && open) {
    panelToggle.style.left = `${mw - 4}px`; // 4px overlap, tab straddles panel's right edge
  } else if (mobile) {
    panelToggle.style.left = "0px"; // flush to screen's left edge, like desktop-collapsed
  } else if (open) {
    panelToggle.style.left = "316px";
  } else {
    panelToggle.style.left = "0px";
  }
}

function updatePanelToggleLabel() {
  const open = isPanelOpen();
  panelToggle.setAttribute("aria-expanded", String(open));
  panelToggle.setAttribute("aria-label", open ? t("panelMinimize") : t("panelExpand"));
  // Arrow shows the direction the panel will move on click:
  //   open  -> ◀ (collapse, slide left)
  //   closed -> ▶ (expand, slide right)
  panelToggle.textContent = open ? "\u25C0" : "\u25B6";
}

function collapsePanel() {
  if (isMobile()) {
    panel.classList.remove("open");
  } else {
    panel.classList.add("collapsed");
  }
  updateTogglePosition();
  updatePanelToggleLabel();
  scheduleInvalidate();
}

function expandPanel() {
  if (isMobile()) {
    panel.classList.add("open");
  } else {
    panel.classList.remove("collapsed");
  }
  updateTogglePosition();
  updatePanelToggleLabel();
  scheduleInvalidate();
}

function togglePanel() {
  isPanelOpen() ? collapsePanel() : expandPanel();
}

panelToggle.addEventListener("click", togglePanel);
panelBackdrop.addEventListener("click", collapsePanel);

window.addEventListener("resize", () => {
  if (isMobile()) {
    panel.classList.remove("collapsed");
  } else {
    panel.classList.remove("open");
  }
  updateTogglePosition();
  updatePanelToggleLabel();
  scheduleInvalidate();
});

// Start collapsed on mobile, open on desktop
collapsePanel();
if (!isMobile()) expandPanel();
updateTogglePosition();
updatePanelToggleLabel();

loadRegions();
