import type { Lang } from "./i18n";

// For SEO: use one canonical production origin in all browser-side metadata.
const ORIGIN = "https://highlinescout.com";

// For SEO: keep the social-card URL, dimensions, and alt text in one shared definition.
export const SOCIAL_CARD = {
  url: `${ORIGIN}/social-card.png`,
  width: "1200",
  height: "630",
  alt: "Highline Scout logo on a forest-green background",
};

export interface SeoPage {
  title: string;
  description: string;
  canonical: string;
  lang: Lang;
  alternates: Record<Lang | "x-default", string>;
}

// For SEO: stable locale URLs let crawlers associate alternate language pages.
const METHODOLOGY_PATHS: Record<Lang, string> = {
  ca: "/ca/how-it-works",
  es: "/es/how-it-works",
  en: "/en/how-it-works",
};

const METHODOLOGY_COPY: Record<Lang, Pick<SeoPage, "title" | "description">> = {
  ca: {
    title: "Com funciona | Highline Scout",
    description: "Descobreix possibles spots de highline per explorar amb Highline Scout.",
  },
  es: {
    title: "Cómo funciona | Highline Scout",
    description: "Descubre posibles spots de highline para explorar con Highline Scout.",
  },
  en: {
    title: "How it works | Highline Scout",
    description: "Find potential highline spots to scout with Highline Scout.",
  },
};

function methodologyPage(lang: Lang): SeoPage {
  const alternates = Object.fromEntries(
    Object.entries(METHODOLOGY_PATHS).map(([code, path]) => [code, `${ORIGIN}${path}`]),
  ) as Record<Lang, string>;

  return {
    ...METHODOLOGY_COPY[lang],
    canonical: `${ORIGIN}${METHODOLOGY_PATHS[lang]}`,
    lang,
    alternates: { ...alternates, "x-default": alternates.en },
  };
}

// For SEO: keep React's metadata aligned with server-rendered crawler metadata.
export function seoForPath(pathname: string): SeoPage {
  const lang = (Object.entries(METHODOLOGY_PATHS) as [Lang, string][]).find(
    ([, path]) => path === pathname,
  )?.[0];
  if (lang) return methodologyPage(lang);

  return {
    title: "HighlineScout | The smarter way to scout your next line",
    description: "Find potential highline spots to scout with Highline Scout.",
    canonical: ORIGIN,
    lang: "en",
    alternates: { ca: ORIGIN, es: ORIGIN, en: ORIGIN, "x-default": ORIGIN },
  };
}
