import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/globals.css";
import { App } from "./App";
import { initAnalytics } from "./lib/analytics";
import { I18nProvider } from "./lib/i18n";

initAnalytics();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
);
