# Final SEO crawler-metadata fix report

## Scope

Fix the methodology pages so non-JavaScript crawlers receive localized HTML
metadata directly from FastAPI, while preserving React hydration. Add complete,
safe English root metadata to the static Vite shell and align the client-side
root title with that approved copy.

## Root cause

The three explicit methodology routes returned `frontend/dist/index.html` as a
`FileResponse`. That static shell had only English root metadata; localized
metadata was created by `SeoHead` after React executed. Crawlers that do not run
JavaScript therefore saw the wrong language, no per-route canonical or
alternates, and no social/schema metadata.

## TDD record

1. Replaced the bare test shell with a realistic `html/head/body` fixture and
   wrote one parametrized test for English, Catalan, and Spanish methodology
   URLs. It asserts the response has the route language, localized title and
   description, canonical URL, all alternates plus `x-default`, Open Graph image
   details, Twitter large-image card, and WebApplication JSON-LD. It also guards
   against an unsafe confirmed-riggable claim.
2. Added a focused test for static `frontend/index.html`, covering its English
   language, approved title, canonical, social card, Twitter card, and schema.
3. `uv run pytest tests/test_seo.py` was RED: all methodology responses were
   the unchanged English shell, and the static root shell lacked canonical and
   social/schema tags (4 failures, 3 passes).
4. Implemented the smallest server change: only the three existing explicit
   methodology routes now read the built shell, replace its `html` language and
   complete `head`, then return `HTMLResponse`. The body and Vite module script
   remain unchanged, so client hydration continues normally. No wildcard route
   was introduced and no Twitter account metadata was added.
5. The first GREEN run revealed an over-escaped word-boundary regex, which left
   Catalan and Spanish documents with `lang=en`. Correcting that one expression
   produced the final green run.

## Metadata decisions

- Copy remains deliberately generic: pages describe potential spots to scout;
  they do not claim confirmed, safe, or riggable lines.
- Social metadata uses the existing 1200×630 card and descriptive alt text.
- JSON-LD is a `WebApplication`; no unverified ratings, pricing, or social
  account is claimed.
- The English static root has the canonical, language alternates, Open Graph,
  Twitter `summary_large_image`, and matching JSON-LD required for non-JS
  crawlers.

## Verification evidence

- `uv run pytest tests/test_seo.py` — 7 passed (one pre-existing TestClient
  deprecation warning).
- `uv run ruff check highliner/server/app.py tests/test_seo.py` — passed.
- `uv run mypy highliner/server/app.py` — passed.
- Frontend Vitest/build could not run in this environment because neither
  `node` nor `npm` is installed or available on `PATH`. The static root contract
  is covered by the Python test above; frontend source changes are limited to
  static metadata and an exact existing title constant.
