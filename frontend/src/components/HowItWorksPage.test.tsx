import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { seoForPath } from "@/lib/seo";
import { HowItWorksPage } from "./HowItWorksPage";

describe("seoForPath", () => {
  it("returns English metadata for the English methodology route", () => {
    expect(seoForPath("/en/how-it-works")).toMatchObject({
      canonical: "https://highlinescout.com/en/how-it-works",
      lang: "en",
    });
  });
});

describe("HowItWorksPage", () => {
  it("renders English source-neutral methodology content", () => {
    render(
      <I18nProvider initialLang="en">
        <HowItWorksPage />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: /how it works/i })).toBeInTheDocument();
    expect(screen.queryByText(/ICGC|MITECO/)).not.toBeInTheDocument();
  });
});
