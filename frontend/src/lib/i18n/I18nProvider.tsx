import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { LANGS, STRINGS, type Lang, type StringKey } from "./strings";

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: StringKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function isLang(value: string | null | undefined): value is Lang {
  return !!value && (LANGS as readonly string[]).includes(value);
}

function pickInitialLang(): Lang {
  try {
    const saved = window.localStorage.getItem("lang");
    if (isLang(saved)) return saved;
  } catch {
    // Storage can be unavailable in private mode.
  }

  const prefs = navigator.languages ?? [navigator.language ?? ""];
  for (const pref of prefs) {
    const code = pref.slice(0, 2).toLowerCase();
    if (isLang(code)) return code;
  }
  return "ca";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => pickInitialLang());

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      window.localStorage.setItem("lang", lang);
    } catch {
      // Ignore unavailable storage.
    }
  }, [lang]);

  const value = useMemo<I18nContextValue>(() => {
    return {
      lang,
      setLang: setLangState,
      t: (key, params) => {
        let value: string = STRINGS[lang][key] ?? key;
        if (params) {
          value = value.replace(/\{(\w+)\}/g, (match, name) =>
            Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
          );
        }
        return value;
      },
    };
  }, [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
