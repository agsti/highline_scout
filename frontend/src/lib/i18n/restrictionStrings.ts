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
        "Plan de Espacios de Interés Natural — el nivel básico de protección en Cataluña (Decreto 328/1992); incluye los espacios de la Red Natura 2000. Régimen urbanístico riguroso; las actividades que puedan lesionar los valores naturales pueden requerir evaluación de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificación de rapaces (aprox. enero-agosto, varía según el espacio).",
      highlight:
        "las actividades que puedan lesionar los valores naturales pueden requerir evaluación de impacto ambiental. Muchos riscos tienen cierres estacionales de escalada por la nidificación de rapaces (aprox. enero-agosto, varía según el espacio).",
    },
    parcs: {
      label: "Parques Naturales",
      tooltip:
        "El nivel de protección más alto (ENPE), cada uno con su propio plan de gestión. Actividades como la escalada, el vivac, los drones y los actos organizados están reguladas y a menudo necesitan autorización del órgano gestor del parque.",
      highlight:
        "Actividades como la escalada, el vivac, los drones y los actos organizados están reguladas y a menudo necesitan autorización del órgano gestor del parque.",
    },
    fauna: {
      label: "Reservas de Fauna",
      tooltip:
        "Reserva Natural de Fauna Salvaje — protege la fauna. Se prohíbe cualquier actividad que pueda perjudicar directa o indirectamente a la fauna protegida; consulte al órgano gestor antes de realizar cualquier actividad.",
      highlight:
        "Se prohíbe cualquier actividad que pueda perjudicar directa o indirectamente a la fauna protegida; consulte al órgano gestor antes de realizar cualquier actividad.",
    },
  },
  en: {
    pein: {
      label: "PEIN",
      tooltip:
        "Plan for Areas of Natural Interest — Catalonia's baseline level of protection (Decree 328/1992); it includes the Natura 2000 network sites. Strict land-use regime; activities that may harm natural values can require an environmental impact assessment. Many cliffs have seasonal climbing closures for raptor nesting (roughly January–August, varies by site).",
      highlight:
        "activities that may harm natural values can require an environmental impact assessment. Many cliffs have seasonal climbing closures for raptor nesting (roughly January–August, varies by site).",
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
        "Wildlife Nature Reserve — protects fauna. Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
      highlight:
        "Any activity that could directly or indirectly harm the protected fauna is forbidden; consult the managing body before doing any activity.",
    },
  },
};

export function restrictionText(id: string, lang: Lang, fallback?: RestrictionText): RestrictionText {
  return RESTRICTION_STRINGS[lang]?.[id] ?? fallback ?? { label: id, tooltip: "", highlight: "" };
}
