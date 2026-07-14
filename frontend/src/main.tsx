import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/globals.css";
import { App } from "./App";
import { HowItWorksPage } from "./components/HowItWorksPage";
import { SeoHead } from "./components/SeoHead";
import { initAnalytics } from "./lib/analytics";
import { I18nProvider } from "./lib/i18n";
import { seoForPath } from "./lib/seo";

void initAnalytics();

// For SEO: these public routes receive localized, indexable methodology content.
const METHODOLOGY_PATHS = new Set(["/ca/how-it-works", "/es/how-it-works", "/en/how-it-works"]);

function normalizePathname(pathname: string) {
  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return normalized === "/" ? normalized : normalized.replace(/\/+$/, "");
}

export function PublicApp({ pathname = window.location.pathname }: { pathname?: string }) {
  const route = normalizePathname(pathname);
  const page = seoForPath(route);
  const methodology = METHODOLOGY_PATHS.has(route);

  return (
    <I18nProvider initialLang={methodology ? page.lang : undefined}>
      <SeoHead page={page} />
      {methodology ? <HowItWorksPage /> : <App />}
    </I18nProvider>
  );
}

const root = document.getElementById("root");
if (root) {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <PublicApp />
    </React.StrictMode>,
  );
}
