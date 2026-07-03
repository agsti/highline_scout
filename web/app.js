const map = L.map("map").setView([41.6, 1.83], 13); // Montserrat area
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
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindPopup(`height ${p.height_min}–${p.height_max} m<br>`
      + `length ${Math.round(p.length_min)}–${Math.round(p.length_max)} m<br>`
      + `${p.n_anchors} anchors · ${p.n_pairs} lines`);
  },
}).addTo(map);

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
  onEachFeature: (f, l) => {
    const p = f.properties;
    // length_min/max are absent (null) in density layers built before length tracking.
    const lenHint = p.length_min == null ? ""
      : ` · ${Math.round(p.length_min)}–${Math.round(p.length_max)} m long`;
    l.bindTooltip(`${p.n_pairs} candidate lines · up to ${Math.round(p.max_exposure)} m${lenHint}`);
  },
}).addTo(map);

// Relative-density key, shown only while the density layer is active.
const densityLegend = L.control({ position: "bottomright" });
densityLegend.onAdd = () => {
  const div = L.DomUtil.create("div", "density-legend");
  const bar = [0, 0.25, 0.5, 0.75, 1]
    .map((t) => `<span style="background:${tealShade(t)}"></span>`).join("");
  div.innerHTML = '<div class="dl-title">Line density</div>'
    + `<div class="dl-bar">${bar}</div>`
    + '<div class="dl-ends"><span>sparse</span><span>dense</span></div>';
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

// Fetch a GeoJSON FeatureCollection, writing user-facing status to `statusEl`.
// Returns the parsed FeatureCollection, or null when the request hit the
// viewport cap (413) or otherwise errored — so callers must skip rendering on
// null instead of assuming a `.features` array.
async function fetchFC(url, statusEl, noun) {
  const res = await fetch(url);
  if (res.status === 413) {
    statusEl.textContent = `zoom in to see ${noun}`;
    return null;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    statusEl.textContent = `error: ${body.detail || res.status}`;
    return null;
  }
  return res.json();
}

const ctrls = ["maxLen", "minExp", "maxDh"];
ctrls.forEach((id) => $(id).addEventListener("input", () => {
  $(id + "V").textContent = $(id).value;
  refresh();
}));
map.on("moveend", refresh);

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
  $("region").addEventListener("change", () => flyToRegion($("region").value));
  if ($("region").value) flyToRegion($("region").value);
  else { refresh(); refreshAnchors(); }
}

async function refreshDensity() {
  const region = $("region").value;
  const z = Math.min(Math.max(Math.round(map.getZoom()) + DENSITY_ZOOM_OFFSET,
                              DENSITY_TILE_MIN), DENSITY_TILE_MAX);
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const params = new URLSearchParams({ region, z, bbox_lonlat: bbox });
  $("status").textContent = "loading hotspots…";
  try {
    const fc = await fetchFC("/density?" + params, $("status"), "hotspots");
    densityLayer.clearLayers();
    if (!fc) return;
    // Rank each cell against the set now in view (styling reads densitySorted).
    densitySorted = fc.features.map((ft) => ft.properties.n_pairs).sort((a, b) => a - b);
    densityLayer.addData(fc);
    showDensityLegend(fc.features.length > 0);
    $("status").textContent = `${fc.features.length} hotspot cells (zoom in for zones)`;
  } catch (e) {
    $("status").textContent = "error: " + e;
  }
}

async function refresh() {
  const region = $("region").value;
  if (!region) return;
  if (map.getZoom() <= DENSITY_MAX_ZOOM) {
    layer.clearLayers();
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
    max_dh: $("maxDh").value,
  });
  $("status").textContent = "searching…";
  try {
    const fc = await fetchFC("/zones?" + params, $("status"), "zones");
    layer.clearLayers();
    if (!fc) return;
    layer.addData(fc);
    $("status").textContent = `${fc.features.length} zones`;
  } catch (e) {
    $("status").textContent = "error: " + e;
  }
}

function anchorPopup(p) {
  const secs = p.sectors
    .map((s) => `drop ${Math.round(s[0])}–${Math.round(s[1])}° (${Math.round(s[2])} m)`)
    .join("<br>");
  return `anchor • elev ${Math.round(p.elev)} m<br>${secs}`;
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
    $("anchorStatus").textContent = "zoom in to see anchors";
    return;
  }
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  try {
    const url = "/anchors?" + new URLSearchParams({ region, bbox_lonlat: bbox });
    const fc = await fetchFC(url, $("anchorStatus"), "anchors");
    if (!fc) {
      anchorLayer.clearLayers();
      return;
    }
    renderAnchors(fc);
    $("anchorStatus").textContent = `${fc.features.length} anchors`;
  } catch (e) {
    anchorLayer.clearLayers();
    $("anchorStatus").textContent = "anchor error: " + e;
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
const restrictionLabel = {}; // layer id -> display label

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
    const fc = await fetchFC(url, $("restrictionStatus"), "protected areas");
    restrictionLayer.clearLayers();
    if (!fc) return;
    restrictionLayer.addData(fc);
    $("restrictionStatus").textContent = `${fc.features.length} protected areas`;
  } catch (e) {
    restrictionLayer.clearLayers();
    $("restrictionStatus").textContent = "error: " + e;
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
    restrictionLabel[rl.id] = rl.label;
    const row = document.createElement("div");
    row.className = "restriction-row";
    const label = document.createElement("label");
    label.className = "restriction";
    label.innerHTML = `<input type="checkbox" data-layer="${rl.id}" /> `
      + `<span class="swatch" style="background:${rl.color}"></span> ${rl.label}`;
    // The description sits inline under the toggle, shown only while the layer
    // is enabled, with the highliner-relevant clause highlighted.
    const desc = document.createElement("p");
    desc.className = "restriction-desc";
    appendDescText(desc, rl.tooltip || "", rl.highlight);
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

map.on("moveend", refreshRestrictions);
loadRestrictionLayers();

loadRegions();
