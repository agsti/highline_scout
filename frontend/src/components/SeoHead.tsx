import { useEffect } from "react";
import type { SeoPage } from "@/lib/seo";

interface SeoHeadProps {
  page: SeoPage;
}

function upsertHeadNode<K extends keyof HTMLElementTagNameMap>(
  tagName: K,
  key: string,
  attributes: Record<string, string>,
  text?: string,
) {
  const selector = `${tagName}[data-seo="${key}"]`;
  const fallback = attributes.name
    ? `${tagName}[name="${attributes.name}"]`
    : attributes.property
      ? `${tagName}[property="${attributes.property}"]`
      : attributes.rel === "canonical"
        ? `${tagName}[rel="canonical"]`
        : null;
  const node =
    document.head.querySelector(selector) ??
    (fallback ? document.head.querySelector(fallback) : null) ??
    document.createElement(tagName);

  node.setAttribute("data-seo", key);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  if (!node.parentElement) document.head.append(node);
}

export function SeoHead({ page }: SeoHeadProps) {
  useEffect(() => {
    const canonical = new URL(page.canonical).toString();
    const title = document.head.querySelector("title") ?? document.createElement("title");
    title.setAttribute("data-seo", "title");
    title.textContent = page.title;
    if (!title.parentElement) document.head.append(title);

    upsertHeadNode("meta", "description", { name: "description", content: page.description });
    upsertHeadNode("link", "canonical", { rel: "canonical", href: canonical });
    upsertHeadNode("meta", "og-title", { property: "og:title", content: page.title });
    upsertHeadNode("meta", "og-description", {
      property: "og:description",
      content: page.description,
    });
    upsertHeadNode("meta", "og-url", { property: "og:url", content: canonical });
    upsertHeadNode("meta", "og-type", { property: "og:type", content: "website" });
    upsertHeadNode("meta", "twitter-card", { name: "twitter:card", content: "summary" });
    upsertHeadNode("meta", "twitter-title", { name: "twitter:title", content: page.title });
    upsertHeadNode("meta", "twitter-description", {
      name: "twitter:description",
      content: page.description,
    });

    for (const [lang, href] of Object.entries(page.alternates)) {
      upsertHeadNode("link", `alternate-${lang}`, { rel: "alternate", hreflang: lang, href });
    }

    upsertHeadNode(
      "script",
      "json-ld",
      { type: "application/ld+json" },
      JSON.stringify({
        "@context": "https://schema.org",
        "@type": "WebApplication",
        name: "HighlineScout",
        url: "https://highlinescout.com/",
        applicationCategory: "TravelApplication",
        publisher: { "@type": "Organization", name: "HighlineScout" },
      }),
    );
  }, [page]);

  return null;
}
