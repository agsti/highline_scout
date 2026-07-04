// Frontend localization catalog. One object per language under STRINGS; LANG
// selects the active one. Loaded before app.js via a plain <script> tag, so
// STRINGS, LANG, t() and applyStaticI18n() are globals — no build step, no
// async load. Adding a language later is one more object under STRINGS.
//
// Only Catalan ships for now. Templates use {name} placeholders filled from the
// params object passed to t(); several strings are HTML (they feed Leaflet
// popups/tooltips, exactly as the pre-i18n code did).
const STRINGS = {
  ca: {
    // --- static panel (index.html [data-i18n]) ---
    region: "Regió",
    maxLength: "Longitud màxima",
    minExposure: "Exposició mínima",
    showAnchors: "Mostra els ancoratges",
    restrictions: "Restriccions",
    caveat: "Zones per explorar — no s'ha confirmat que es puguin equipar. "
      + "No s'han verificat ancoratges, arbres, roca solta, accessos ni permisos.",

    // --- status line ---
    searching: "cercant…",
    loadingHotspots: "carregant punts d'interès…",
    zonesCount: "{n} zones",
    hotspotCells: "{n} cel·les de punts d'interès (amplia per veure zones)",
    anchorsCount: "{n} ancoratges",
    protectedAreasCount: "{n} espais protegits",
    zoomInToSee: "amplia per veure {noun}",
    error: "error: {detail}",
    anchorError: "error d'ancoratges: {detail}",

    // nouns injected into zoomInToSee
    nounZones: "zones",
    nounHotspots: "punts d'interès",
    nounAnchors: "ancoratges",
    nounProtectedAreas: "espais protegits",

    // --- popups / tooltips (HTML) ---
    zonePopup: "alçada {min}–{max} m<br>longitud {lmin}–{lmax} m<br>"
      + "{na} ancoratges · {np} línies",
    densityTooltip: "{n} línies candidates · fins a {max} m{lenHint}",
    densityLenHint: " · {min}–{max} m de llarg",
    anchorPopup: "ancoratge • elev {elev} m<br>{sectors}",
    anchorSector: "caiguda {a}–{b}° ({drop} m)",

    // --- density legend ---
    lineDensity: "Densitat de línies",
    sparse: "escàs",
    dense: "dens",
  },
};

let LANG = "ca";

// Look up a string by key for the active language and interpolate {name}
// placeholders from params. A missing key returns the key itself, so gaps are
// visible on screen rather than silently blank.
function t(key, params) {
  let s = (STRINGS[LANG] && STRINGS[LANG][key]);
  if (s == null) return key;
  if (params) {
    s = s.replace(/\{(\w+)\}/g, (m, name) =>
      (name in params ? params[name] : m));
  }
  return s;
}

// Populate every [data-i18n] element's text from the catalog. Called once on
// load; the script is synchronous and sits after the panel markup, so the
// elements exist by the time this runs.
function applyStaticI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
}
