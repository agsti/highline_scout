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
    ch_game_reserves: {
      label: "Reservas federales de fauna",
      tooltip:
        "Reserva federal de caza vedada que protege mamíferos silvestres, aves y sus hábitats, con zonas de protección integral o parcial. El acceso y las actividades recreativas pueden estar restringidos; consulta la ficha de la reserva y al cantón antes de instalar.",
      highlight:
        "El acceso y las actividades recreativas pueden estar restringidos; consulta la ficha de la reserva y al cantón antes de instalar.",
    },
    ch_bird_reserves: {
      label: "Reservas de aves acuáticas y migratorias",
      tooltip:
        "Reserva federal de importancia internacional o nacional para aves acuáticas y migratorias. El acceso, los deportes acuáticos y las molestias a la fauna pueden estar restringidos; consulta la ficha de la reserva y al cantón antes de instalar.",
      highlight:
        "El acceso, los deportes acuáticos y las molestias a la fauna pueden estar restringidos; consulta la ficha de la reserva y al cantón antes de instalar.",
    },
    ch_parks: {
      label: "Parques nacionales y regionales suizos",
      tooltip:
        "Parque Nacional Suizo o parque de importancia nacional. El highline no está prohibido automáticamente en todo el parque, pero las zonas protegidas y las normas locales pueden regular el acceso, los anclajes y las actividades organizadas; consulta a la dirección del parque antes de instalar.",
      highlight:
        "El highline no está prohibido automáticamente en todo el parque, pero las zonas protegidas y las normas locales pueden regular el acceso, los anclajes y las actividades organizadas; consulta a la dirección del parque antes de instalar.",
    },
    cl_snaspe: {
      label: "SNASPE (Parques y Reservas Nacionales)",
      tooltip:
        "Parque nacional, reserva nacional, monumento natural o reserva forestal administrado por CONAF (Sistema Nacional de Áreas Silvestres Protegidas del Estado). El ingreso suele requerir permiso/pago, y CONAF puede restringir o prohibir la escalada, el vivac y los anclajes fijos en una unidad concreta; consulta con la administración del parque antes de instalar.",
      highlight:
        "El ingreso suele requerir permiso/pago, y CONAF puede restringir o prohibir la escalada, el vivac y los anclajes fijos en una unidad concreta; consulta con la administración del parque antes de instalar.",
    },
    cl_santuario: {
      label: "Santuarios de la Naturaleza y Reservas de la Biósfera",
      tooltip:
        "Santuario de la Naturaleza, reserva de la biósfera o paisaje de conservación - una designación del Ministerio del Medio Ambiente que puede aplicarse a terrenos privados. Según la Ley de Monumentos Nacionales, instalar anclajes fijos aquí sin autorización previa del Consejo de Monumentos Nacionales es un delito legal, no solo una norma del parque.",
      highlight:
        "Según la Ley de Monumentos Nacionales, instalar anclajes fijos aquí sin autorización previa del Consejo de Monumentos Nacionales es un delito legal, no solo una norma del parque.",
    },
    cl_conservacion_privada: {
      label: "Conservación Privada y Comunitaria",
      tooltip:
        "Terreno de conservación privado o comunitario, u otro terreno estatal protegido fuera del SNASPE. El acceso, el camping y la instalación dependen del propietario, no de un organismo público; consigue su permiso antes de instalar.",
      highlight:
        "El acceso, el camping y la instalación dependen del propietario, no de un organismo público; consigue su permiso antes de instalar.",
    },
    dk_spa: {
      label: "ZEPA (Dinamarca)",
      tooltip: "Zona danesa de Especial Protección para las Aves (Natura 2000, Directiva Aves). Los acantilados y peñascos costeros pueden tener restricciones estacionales de acceso para evitar molestias a aves nidificantes; confirma las normas locales antes de instalar.",
      highlight: "Los acantilados y peñascos costeros pueden tener restricciones estacionales de acceso para evitar molestias a aves nidificantes; confirma las normas locales antes de instalar.",
    },
    dk_sac: {
      label: "ZEC (Dinamarca)",
      tooltip: "Zona danesa de Especial Conservación (Natura 2000, Directiva Hábitats). La instalación o el acceso que dañe un hábitat protegido puede estar regulado; consulta el plan de gestión antes de instalar.",
      highlight: "La instalación o el acceso que dañe un hábitat protegido puede estar regulado; consulta el plan de gestión antes de instalar.",
    },
    dk_protected: {
      label: "Áreas protegidas (Dinamarca)",
      tooltip: "Área danesa protegida a nivel nacional. Su orden de protección puede restringir el acceso, la escalada, los anclajes fijos, el vivac y las actividades organizadas; consulta a la autoridad responsable antes de instalar.",
      highlight: "Su orden de protección puede restringir el acceso, la escalada, los anclajes fijos, el vivac y las actividades organizadas; consulta a la autoridad responsable antes de instalar.",
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
    ch_game_reserves: {
      label: "Reserves federals de fauna",
      tooltip:
        "Reserva federal de caça vedada que protegeix mamífers salvatges, aus i els seus hàbitats, amb zones de protecció integral o parcial. L'accés i les activitats recreatives poden estar restringits; consulteu la fitxa de la reserva i el cantó abans d'instal·lar.",
      highlight:
        "L'accés i les activitats recreatives poden estar restringits; consulteu la fitxa de la reserva i el cantó abans d'instal·lar.",
    },
    ch_bird_reserves: {
      label: "Reserves d'aus aquàtiques i migratòries",
      tooltip:
        "Reserva federal d'importància internacional o nacional per a aus aquàtiques i migratòries. L'accés, els esports aquàtics i les molèsties a la fauna poden estar restringits; consulteu la fitxa de la reserva i el cantó abans d'instal·lar.",
      highlight:
        "L'accés, els esports aquàtics i les molèsties a la fauna poden estar restringits; consulteu la fitxa de la reserva i el cantó abans d'instal·lar.",
    },
    ch_parks: {
      label: "Parcs nacionals i regionals suïssos",
      tooltip:
        "Parc Nacional Suís o parc d'importància nacional. El highline no està prohibit automàticament a tot el parc, però les zones protegides i les normes locals poden regular l'accés, els ancoratges i les activitats organitzades; consulteu la direcció del parc abans d'instal·lar.",
      highlight:
        "El highline no està prohibit automàticament a tot el parc, però les zones protegides i les normes locals poden regular l'accés, els ancoratges i les activitats organitzades; consulteu la direcció del parc abans d'instal·lar.",
    },
    cl_snaspe: {
      label: "SNASPE (Parcs i Reserves Nacionals)",
      tooltip:
        "Parc nacional, reserva nacional, monument natural o reserva forestal administrat per CONAF (Sistema Nacional de Àrees Silvestres Protegides de l'Estat). L'entrada sol requerir permís/pagament, i CONAF pot restringir o prohibir l'escalada, el vivac i els ancoratges fixos en una unitat concreta; consulteu l'administració del parc abans d'instal·lar.",
      highlight:
        "L'entrada sol requerir permís/pagament, i CONAF pot restringir o prohibir l'escalada, el vivac i els ancoratges fixos en una unitat concreta; consulteu l'administració del parc abans d'instal·lar.",
    },
    cl_santuario: {
      label: "Santuaris de la Natura i Reserves de la Biosfera",
      tooltip:
        "Santuari de la Natura, reserva de la biosfera o paisatge de conservació - una designació del Ministeri del Medi Ambient que pot aplicar-se a terrenys privats. Segons la Llei de Monuments Nacionals, instal·lar ancoratges fixos aquí sense autorització prèvia del Consell de Monuments Nacionals és un delicte legal, no només una norma del parc.",
      highlight:
        "Segons la Llei de Monuments Nacionals, instal·lar ancoratges fixos aquí sense autorització prèvia del Consell de Monuments Nacionals és un delicte legal, no només una norma del parc.",
    },
    cl_conservacion_privada: {
      label: "Conservació Privada i Comunitària",
      tooltip:
        "Terreny de conservació privat o comunitari, o altre terreny estatal protegit fora del SNASPE. L'accés, l'acampada i la instal·lació depenen del propietari, no d'un organisme públic; aconseguiu el seu permís abans d'instal·lar.",
      highlight:
        "L'accés, l'acampada i la instal·lació depenen del propietari, no d'un organisme públic; aconseguiu el seu permís abans d'instal·lar.",
    },
    dk_spa: {
      label: "ZEPA (Dinamarca)",
      tooltip: "Zona danesa d'Especial Protecció per a les Aus (Natura 2000, Directiva Aus). Els penya-segats i cingles costaners poden tenir restriccions estacionals d'accés per evitar molèsties a les aus nidificants; confirmeu les normes locals abans d'instal·lar.",
      highlight: "Els penya-segats i cingles costaners poden tenir restriccions estacionals d'accés per evitar molèsties a les aus nidificants; confirmeu les normes locals abans d'instal·lar.",
    },
    dk_sac: {
      label: "ZEC (Dinamarca)",
      tooltip: "Zona danesa d'Especial Conservació (Natura 2000, Directiva Hàbitats). La instal·lació o l'accés que malmeti un hàbitat protegit pot estar regulat; consulteu el pla de gestió abans d'instal·lar.",
      highlight: "La instal·lació o l'accés que malmeti un hàbitat protegit pot estar regulat; consulteu el pla de gestió abans d'instal·lar.",
    },
    dk_protected: {
      label: "Àrees protegides (Dinamarca)",
      tooltip: "Àrea danesa protegida a escala nacional. La seva ordre de protecció pot restringir l'accés, l'escalada, els ancoratges fixos, el vivac i les activitats organitzades; consulteu l'autoritat responsable abans d'instal·lar.",
      highlight: "La seva ordre de protecció pot restringir l'accés, l'escalada, els ancoratges fixos, el vivac i les activitats organitzades; consulteu l'autoritat responsable abans d'instal·lar.",
    },
  },
};

export function restrictionText(id: string, lang: Lang, fallback?: RestrictionText): RestrictionText {
  return RESTRICTION_STRINGS[lang]?.[id] ?? fallback ?? { label: id, tooltip: "", highlight: "" };
}
