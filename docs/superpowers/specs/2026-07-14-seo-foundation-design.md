# SEO foundation design

## Goal

Make HighlineScout discoverable without changing the map-first product
experience. Search-facing language is English-first and the site is positioned
globally, while the product remains precise about results being potential spots
to scout rather than confirmed, ranked, or riggable lines.

## Public URLs

- `https://highlinescout.com/` remains the interactive map and is the
  canonical homepage. `www.highlinescout.com` redirects to the apex domain.
- The map defaults to English. Its title is `HighlineScout | The smarter way to
  scout your next line`.
- The indexable methodology pages are:
  - `/en/how-it-works`
  - `/ca/how-it-works`
  - `/es/how-it-works`
- The server explicitly returns the frontend shell for these three deep links
  in production. This avoids the root static mount returning a 404 while Vite's
  normal SPA fallback continues to serve them locally.

## Metadata and indexing

- Each public page gets an absolute canonical URL, a language-appropriate
  title and description, Open Graph metadata, and Twitter card metadata.
- The methodology pages have reciprocal `hreflang` links for English, Catalan,
  and Spanish, plus `x-default` pointing to the English page. The homepage has
  no locale-variant URL in this iteration.
- `robots.txt` permits public pages and references
  `https://highlinescout.com/sitemap.xml`. It prevents crawler discovery of
  API endpoints but is not used as access control.
- `sitemap.xml` contains exactly the homepage and the three methodology pages;
  parameterized map URLs and API endpoints are excluded.
- JSON-LD declares a `WebApplication` published by `HighlineScout`. It makes
  no claims that spots are verified, globally available, or best-ranked.

## Methodology content and navigation

- Each methodology page is a localized, static frontend view. It explains the
  terrain-data workflow (potential anchors and gaps grouped into scouting
  zones), the in-person validation requirement, and generic terrain and
  protected-area data provenance. It deliberately does not name individual
  sources.
- The exact safety caveat covers anchors, terrain, access, permissions, and
  suitability. It never encourages users to rely on the tool for rigging
  decisions.
- The menu gains a visible “How it works” link. The existing About dialog stays
  as the short product and privacy summary.
- Switching language on a methodology page navigates to its matching
  locale-specific URL. Map language selection remains client-side.

## Social sharing

- A 1200x630 branded Open Graph image is created from the existing logo and
  used for every page. No `twitter:site` value is emitted because the project
  has no X/Twitter account.

## Verification

- Frontend tests cover metadata, language alternates, structured data, the
  English default, and the new navigation.
- Backend tests cover `robots.txt`, `sitemap.xml`, and production deep-route
  serving.
- After deployment, submit the sitemap in Google Search Console, inspect the
  homepage and all three methodology URLs, and verify the `www` redirect lands
  on the apex canonical URL.
