import type { Lang } from "./strings";

export interface RestrictionText {
  label: string;
  tooltip: string;
  highlight: string;
}

export const RESTRICTION_STRINGS: Partial<Record<Lang, Record<string, RestrictionText>>> = {
  es: {
    zepa: {
      label: "ZEPA (Aves)",
      tooltip:
        "Zona de Especial Protección para las Aves — Red Natura 2000 (Directiva Aves). Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
      highlight:
        "Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
    },
    zec: {
      label: "ZEC / LIC",
      tooltip:
        "Lugar de Importancia Comunitaria / Zona Especial de Conservación — Red Natura 2000 (Directiva Hábitats). Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
      highlight:
        "Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
    },
    enp: {
      label: "Espacios Naturales Protegidos",
      tooltip:
        "Espacio Natural Protegido — una figura de protección estatal o autonómica como un parque nacional o natural, una reserva natural o un monumento natural, cada uno con su propio plan de gestión. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    },
    zps: {
      label: "ZPS (Aves)",
      tooltip:
        "Zona de Protección Especial para las Aves — Natura 2000 (Directiva Aves; ZPS italiana). Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
      highlight:
        "Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
    },
    zsc: {
      label: "ZSC / SIC",
      tooltip:
        "Lugar de Importancia Comunitaria / Zona Especial de Conservación — Natura 2000 (Directiva Hábitats; ZSC/SIC italiana). Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
      highlight:
        "Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
    },
    euap: {
      label: "Áreas Protegidas (EUAP)",
      tooltip:
        "Área natural protegida del elenco oficial italiano (EUAP) — un parque nacional o regional, una reserva natural u otra figura de protección, cada una con sus propias normas y órgano gestor. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    },
    fr_zps: {
      label: "ZPS (Aves)",
      tooltip:
        "Zona de Protección Especial para las Aves — Natura 2000 (Directiva Aves; ZPS francesa). Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
      highlight:
        "Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
    },
    fr_zsc: {
      label: "ZSC / SIC",
      tooltip:
        "Lugar de Importancia Comunitaria / Zona Especial de Conservación — Natura 2000 (Directiva Hábitats; ZSC/SIC francesa). Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
      highlight:
        "Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
    },
    fr_ep: {
      label: "Áreas Protegidas (PN / RN / APPB)",
      tooltip:
        "Área protegida reglamentaria francesa — el corazón de un parque nacional, una reserva natural nacional o regional, o un decreto de protección de biotopo (APPB), cada uno con sus propias normas y órgano gestor. Los APPB en particular respaldan muchos cierres de cortados. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    },
  },
  ca: {
    zepa: {
      label: "ZEPA (Aus)",
      tooltip:
        "Zona d'Especial Protecció per a les Aus — Xarxa Natura 2000 (Directiva Aus). Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
      highlight:
        "Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
    },
    zec: {
      label: "ZEC / LIC",
      tooltip:
        "Lloc d'Importància Comunitària / Zona Especial de Conservació — Xarxa Natura 2000 (Directiva Hàbitats). Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
      highlight:
        "Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
    },
    enp: {
      label: "Espais Naturals Protegits",
      tooltip:
        "Espai Natural Protegit — una figura de protecció estatal o autonòmica com un parc nacional o natural, una reserva natural o un monument natural, cadascun amb el seu pla de gestió. L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
      highlight:
        "L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
    },
    zps: {
      label: "ZPS (Aus)",
      tooltip:
        "Zona de Protecció Especial per a les Aus — Natura 2000 (Directiva Aus; ZPS italiana). Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
      highlight:
        "Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
    },
    zsc: {
      label: "ZSC / SIC",
      tooltip:
        "Lloc d'Importància Comunitària / Zona Especial de Conservació — Natura 2000 (Directiva Hàbitats; ZSC/SIC italiana). Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
      highlight:
        "Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
    },
    euap: {
      label: "Àrees Protegides (EUAP)",
      tooltip:
        "Àrea natural protegida de l'elenc oficial italià (EUAP) — un parc nacional o regional, una reserva natural o una altra figura de protecció, cadascuna amb les seves normes i òrgan gestor. L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
      highlight:
        "L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
    },
    fr_zps: {
      label: "ZPS (Aus)",
      tooltip:
        "Zona de Protecció Especial per a les Aus — Natura 2000 (Directiva Aus; ZPS francesa). Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
      highlight:
        "Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
    },
    fr_zsc: {
      label: "ZSC / SIC",
      tooltip:
        "Lloc d'Importància Comunitària / Zona Especial de Conservació — Natura 2000 (Directiva Hàbitats; ZSC/SIC francesa). Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
      highlight:
        "Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
    },
    fr_ep: {
      label: "Àrees Protegides (PN / RN / APPB)",
      tooltip:
        "Àrea protegida reglamentària francesa — el cor d'un parc nacional, una reserva natural nacional o regional, o un decret de protecció de biòtop (APPB), cadascun amb les seves normes i òrgan gestor. Els APPB en particular sustenten molts tancaments de cingles. L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
      highlight:
        "L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
    },
  },
};

export function restrictionText(id: string, lang: Lang, fallback?: RestrictionText): RestrictionText {
  return RESTRICTION_STRINGS[lang]?.[id] ?? fallback ?? { label: id, tooltip: "", highlight: "" };
}
