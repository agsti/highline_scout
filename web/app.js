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

const $ = (id) => document.getElementById(id);
const ctrls = ["maxLen", "minExp", "maxDh"];
ctrls.forEach((id) => $(id).addEventListener("input", () => {
  $(id + "V").textContent = $(id).value;
  refresh();
}));
map.on("moveend", refresh);

async function loadRegions() {
  const r = await fetch("/regions").then((x) => x.json());
  r.regions.forEach((name) => {
    const o = document.createElement("option");
    o.value = o.textContent = name;
    $("region").appendChild(o);
  });
  $("region").addEventListener("change", refresh);
  refresh();
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
    const fc = await fetch("/candidates?" + params).then((x) => x.json());
    layer.clearLayers();
    layer.addData(fc);
    $("status").textContent = `${fc.features.length} candidates`;
  } catch (e) {
    $("status").textContent = "error: " + e;
  }
}

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
    refresh();
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
