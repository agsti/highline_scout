import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./App", () => ({ App: () => <main>Map</main> }));

import { PublicApp } from "./main";

function renderPublicApp(pathname: string) {
  return render(<PublicApp pathname={pathname} />);
}

describe("PublicApp", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    document.head.querySelectorAll("[data-seo]").forEach((node) => node.remove());
  });

  it("defaults the map to English with an apex canonical URL", () => {
    renderPublicApp("/");

    expect(document.documentElement.lang).toBe("en");
    expect(document.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(
      "https://highlinescout.com/",
    );
  });

  it("renders localized methodology metadata without duplicating alternates", () => {
    renderPublicApp("/ca/how-it-works");

    expect(document.querySelectorAll('link[rel="alternate"][hreflang]')).toHaveLength(4);
    expect(document.querySelector('meta[name="twitter:site"]')).not.toBeInTheDocument();
    expect(document.querySelector('script[type="application/ld+json"]')?.textContent).toContain(
      '"@type":"WebApplication"',
    );
  });

  it("replaces unmarked alternate links and JSON-LD", () => {
    for (const lang of ["ca", "es", "en", "x-default"]) {
      const alternate = document.createElement("link");
      alternate.rel = "alternate";
      alternate.hreflang = lang;
      alternate.href = "https://old.example/";
      document.head.append(alternate);
    }
    const jsonLd = document.createElement("script");
    jsonLd.type = "application/ld+json";
    jsonLd.textContent = '{"@type":"Organization"}';
    document.head.append(jsonLd);

    renderPublicApp("/ca/how-it-works");

    for (const lang of ["ca", "es", "en", "x-default"]) {
      expect(
        document.head.querySelectorAll(`link[rel="alternate"][hreflang="${lang}"]`),
      ).toHaveLength(1);
    }
    expect(document.head.querySelectorAll('script[type="application/ld+json"]')).toHaveLength(1);
    expect(document.head.querySelector('script[type="application/ld+json"]')?.textContent).toContain(
      '"@type":"WebApplication"',
    );
  });
});
