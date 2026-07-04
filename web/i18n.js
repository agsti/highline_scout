// Frontend localization catalog. One object per language under STRINGS; LANG
// selects the active one. Loaded before app.js via a plain <script> tag, so
// STRINGS, LANG, t(), setLang() and applyStaticI18n() are globals — no build
// step, no async load. Adding a language is one more object under STRINGS
// (every catalog must define the same key set; see the parity check below).
//
// Templates use {name} placeholders filled from the params object passed to
// t(); several strings are HTML (they feed Leaflet popups/tooltips, exactly as
// the pre-i18n code did).
const STRINGS = {
  ca: {
    language: "Idioma",
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

  es: {
    language: "Idioma",
    region: "Región",
    maxLength: "Longitud máxima",
    minExposure: "Exposición mínima",
    showAnchors: "Mostrar anclajes",
    restrictions: "Restricciones",
    caveat: "Zonas para explorar — no se ha confirmado que se puedan montar. "
      + "No se han verificado anclajes, árboles, roca suelta, accesos ni permisos.",
    searching: "buscando…",
    loadingHotspots: "cargando puntos de interés…",
    zonesCount: "{n} zonas",
    hotspotCells: "{n} celdas de puntos de interés (amplía para ver zonas)",
    anchorsCount: "{n} anclajes",
    protectedAreasCount: "{n} espacios protegidos",
    zoomInToSee: "amplía para ver {noun}",
    error: "error: {detail}",
    anchorError: "error de anclajes: {detail}",
    nounZones: "zonas",
    nounHotspots: "puntos de interés",
    nounAnchors: "anclajes",
    nounProtectedAreas: "espacios protegidos",
    zonePopup: "altura {min}–{max} m<br>longitud {lmin}–{lmax} m<br>"
      + "{na} anclajes · {np} líneas",
    densityTooltip: "{n} líneas candidatas · hasta {max} m{lenHint}",
    densityLenHint: " · {min}–{max} m de largo",
    anchorPopup: "anclaje • elev {elev} m<br>{sectors}",
    anchorSector: "caída {a}–{b}° ({drop} m)",
    lineDensity: "Densidad de líneas",
    sparse: "escaso",
    dense: "denso",
  },

  en: {
    language: "Language",
    region: "Region",
    maxLength: "Max length",
    minExposure: "Min exposure",
    showAnchors: "Show anchors",
    restrictions: "Restrictions",
    caveat: "Zones to scout — not confirmed-riggable. No bolts, trees, "
      + "loose rock, access or permissions are verified.",
    searching: "searching…",
    loadingHotspots: "loading hotspots…",
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
    zonePopup: "height {min}–{max} m<br>length {lmin}–{lmax} m<br>"
      + "{na} anchors · {np} lines",
    densityTooltip: "{n} candidate lines · up to {max} m{lenHint}",
    densityLenHint: " · {min}–{max} m long",
    anchorPopup: "anchor • elev {elev} m<br>{sectors}",
    anchorSector: "drop {a}–{b}° ({drop} m)",
    lineDensity: "Line density",
    sparse: "sparse",
    dense: "dense",
  },
};

// Translations for the protected-area restriction layers (label / tooltip /
// highlighted clause), keyed by layer id. Catalan is intentionally absent: it
// comes from the backend (see restrictionText's fallback), so it is never
// duplicated here. Per language, `highlight` MUST be a verbatim substring of
// `tooltip` — the panel description marks it with indexOf().
const RESTRICTION_STRINGS = {
  es: {
    pein: {
      label: "PEIN",
      tooltip: "Plan de Espacios de Interés Natural — el nivel básico de "
        + "protección en Cataluña (Decreto 328/1992); incluye los espacios de "
        + "la Red Natura 2000. Régimen urbanístico riguroso; las actividades "
        + "que puedan lesionar los valores naturales pueden requerir evaluación "
        + "de impacto ambiental. Muchos riscos tienen cierres estacionales de "
        + "escalada por la nidificación de rapaces (aprox. enero-agosto, varía "
        + "según el espacio).",
      highlight: "las actividades que puedan lesionar los valores naturales "
        + "pueden requerir evaluación de impacto ambiental. Muchos riscos "
        + "tienen cierres estacionales de escalada por la nidificación de "
        + "rapaces (aprox. enero-agosto, varía según el espacio).",
    },
    parcs: {
      label: "Parques Naturales",
      tooltip: "El nivel de protección más alto (ENPE), cada uno con su propio "
        + "plan de gestión. Actividades como la escalada, el vivac, los drones "
        + "y los actos organizados están reguladas y a menudo necesitan "
        + "autorización del órgano gestor del parque.",
      highlight: "Actividades como la escalada, el vivac, los drones y los "
        + "actos organizados están reguladas y a menudo necesitan autorización "
        + "del órgano gestor del parque.",
    },
    fauna: {
      label: "Reservas de Fauna",
      tooltip: "Reserva Natural de Fauna Salvaje — protege la fauna. Se prohíbe "
        + "cualquier actividad que pueda perjudicar directa o indirectamente a "
        + "la fauna protegida; consulte al órgano gestor antes de realizar "
        + "cualquier actividad.",
      highlight: "Se prohíbe cualquier actividad que pueda perjudicar directa o "
        + "indirectamente a la fauna protegida; consulte al órgano gestor antes "
        + "de realizar cualquier actividad.",
    },
  },
  en: {
    pein: {
      label: "PEIN",
      tooltip: "Plan for Areas of Natural Interest — Catalonia's baseline level "
        + "of protection (Decree 328/1992); it includes the Natura 2000 network "
        + "sites. Strict land-use regime; activities that may harm natural "
        + "values can require an environmental impact assessment. Many cliffs "
        + "have seasonal climbing closures for raptor nesting (roughly "
        + "January–August, varies by site).",
      highlight: "activities that may harm natural values can require an "
        + "environmental impact assessment. Many cliffs have seasonal climbing "
        + "closures for raptor nesting (roughly January–August, varies by site).",
    },
    parcs: {
      label: "Nature Parks",
      tooltip: "The highest level of protection (ENPE), each with its own "
        + "management plan. Activities such as climbing, bivouacking, drones "
        + "and organized events are regulated and often need authorization from "
        + "the park's managing body.",
      highlight: "Activities such as climbing, bivouacking, drones and "
        + "organized events are regulated and often need authorization from the "
        + "park's managing body.",
    },
    fauna: {
      label: "Wildlife Reserves",
      tooltip: "Wildlife Nature Reserve — protects fauna. Any activity that "
        + "could directly or indirectly harm the protected fauna is forbidden; "
        + "consult the managing body before doing any activity.",
      highlight: "Any activity that could directly or indirectly harm the "
        + "protected fauna is forbidden; consult the managing body before doing "
        + "any activity.",
    },
  },
};

// Resolve a restriction layer's text for the active language. `fallback` is the
// server-provided (Catalan) {label,tooltip,highlight}; it is used for `ca` and
// for any layer without a translation, so backend-added layers degrade to
// Catalan rather than breaking.
function restrictionText(id, fallback) {
  const tr = RESTRICTION_STRINGS[LANG] && RESTRICTION_STRINGS[LANG][id];
  return tr || fallback || {};
}

// Pick the language to start in: a remembered choice wins, else the browser's
// preferred language (matched by 2-letter prefix), else Catalan. localStorage
// can throw (private mode / disabled), so every access is guarded.
function pickInitialLang() {
  try {
    const saved = localStorage.getItem("lang");
    if (saved && saved in STRINGS) return saved;
  } catch (e) { /* storage unavailable — fall through to detection */ }
  const prefs = navigator.languages || [navigator.language || ""];
  for (const p of prefs) {
    const code = (p || "").slice(0, 2).toLowerCase();
    if (code in STRINGS) return code;
  }
  return "ca";
}

let LANG = pickInitialLang();
if (typeof document !== "undefined") document.documentElement.lang = LANG;

// Switch the active language: update LANG, remember it, and reflect it on the
// <html> element. Callers re-render the UI (static labels + dynamic layers).
function setLang(lang) {
  if (!(lang in STRINGS)) return;
  LANG = lang;
  try { localStorage.setItem("lang", lang); } catch (e) { /* ignore */ }
  document.documentElement.lang = lang;
}

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

// Populate every [data-i18n] element's text from the catalog. Called on load
// and again after each language switch.
function applyStaticI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
}

// Dev-only guard: every catalog must define exactly the same key set as `ca`,
// so a switch never lands on an untranslated (key-echoed) string. Logs, never
// throws — a missing key still degrades gracefully via t()'s fallback.
(function assertCatalogParity() {
  const base = Object.keys(STRINGS.ca).sort().join(",");
  for (const lang of Object.keys(STRINGS)) {
    const keys = Object.keys(STRINGS[lang]).sort().join(",");
    if (keys !== base && typeof console !== "undefined") {
      console.warn(`i18n: catalog "${lang}" key set differs from "ca"`);
    }
  }
})();
