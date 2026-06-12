const map = L.map("map").setView([41.6, 1.83], 13); // Montserrat area
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);

const layer = L.geoJSON(null, {
  style: { color: "#e6005c", weight: 3 },
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindPopup(`length ${p.length} m<br>exposure ${p.exposure} m<br>`
      + `Δh ${p.height_diff} m<br>score ${p.score}`);
  },
}).addTo(map);

const ANCHOR_COLOR = "#1f9e8f";
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

async function refresh() {
  const region = $("region").value;
  if (!region) return;
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
    const fc = await fetchFC("/candidates?" + params, $("status"), "candidates");
    layer.clearLayers();
    if (!fc) return;
    layer.addData(fc);
    $("status").textContent = `${fc.features.length} candidates`;
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
// Drawn in a dedicated pane below the candidate lines and anchor markers so the
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

function addRegionOption(name) {
  if ([...$("region").options].some((o) => o.value === name)) return;
  const o = document.createElement("option");
  o.value = o.textContent = name;
  $("region").appendChild(o);
}

async function pollJob(jobId) {
  const job = await fetch("/jobs/" + jobId).then((x) => x.json());
  if (job.status === "queued") {
    $("jobStatus").textContent = "queued…";
  } else if (job.status === "running") {
    $("jobStatus").textContent = job.phase === "downloading"
      ? `downloading ${job.done}/${job.total} tiles…`
      : "extracting anchors…";
  } else if (job.status === "done") {
    $("jobStatus").textContent = job.message || "done";
    addRegionOption(job.region);
    $("region").value = job.region;
    $("analyzeBtn").disabled = false;
    await fetchRegions();      // pick up the new region's bounds
    flyToRegion(job.region);   // fitBounds -> moveend -> refresh
    return;
  } else if (job.status === "error") {
    $("jobStatus").textContent = "error: " + job.error;
    $("analyzeBtn").disabled = false;
    return;
  }
  setTimeout(() => pollJob(jobId), 1000);
}

$("analyzeBtn").addEventListener("click", async () => {
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  $("analyzeBtn").disabled = true;
  $("jobStatus").textContent = "submitting…";
  try {
    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("regionName").value, bbox_lonlat: bbox }),
    });
    if (!res.ok) {
      $("jobStatus").textContent = "error: " + (await res.text());
      $("analyzeBtn").disabled = false;
      return;
    }
    pollJob((await res.json()).job_id);
  } catch (e) {
    $("jobStatus").textContent = "error: " + e;
    $("analyzeBtn").disabled = false;
  }
});
