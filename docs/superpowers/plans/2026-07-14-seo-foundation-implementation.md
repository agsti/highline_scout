# SEO Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HighlineScout’s map-first site indexable, English-first, shareable, and supported by localized safety-first methodology pages.

**Architecture:** FastAPI owns crawler files and explicit production SPA fallbacks. React selects the map or a static methodology page from the pathname; one reusable component owns document tags and JSON-LD. Vite copies the social image to the production build.

**Tech Stack:** FastAPI/Starlette, React 18, TypeScript, Vite, Vitest, pytest, Tailwind CSS.

## Global Constraints

- Canonical origin: `https://highlinescout.com`; deployment redirects `www` to this origin.
- `/` stays the map and defaults to English.
- Only `/en/how-it-works`, `/ca/how-it-works`, and `/es/how-it-works` are localized public pages.
- Results are potential spots to scout, never verified, best-ranked, or globally available lines.
- Methodology copy names no individual terrain or protected-area provider.
- Add no cookies, identity tracking, or X/Twitter account metadata.

---

### Task 1: Backend crawler endpoints and deep links

**Files:**
- Modify: `highliner/server/app.py`
- Create: `tests/test_seo.py`

**Interfaces:**
- Produces `GET /robots.txt`, `GET /sitemap.xml`, and a frontend-shell response for the three methodology paths when `frontend/dist/index.html` exists.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_sitemap_lists_only_public_urls(client: TestClient) -> None:
    assert client.get("/robots.txt").status_code == 200
    sitemap = client.get("/sitemap.xml")
    assert "/en/how-it-works" in sitemap.text
    assert "/zones" not in sitemap.text

@pytest.mark.parametrize("path", ["/en/how-it-works", "/ca/how-it-works", "/es/how-it-works"])
def test_methodology_routes_return_built_shell(client: TestClient, path: str) -> None:
    assert client.get(path).text == "<html>shell</html>"
```

- [ ] **Step 2: Verify the failing test**

Run: `uv run pytest tests/test_seo.py -v`

Expected: FAIL because the handlers do not exist.

- [ ] **Step 3: Add exact SEO handlers before `app.mount("/", ...)`**

Use `PlainTextResponse` for robots and `Response(media_type="application/xml")` for the four-URL sitemap. Add a private frontend-directory helper so tests can patch it. Add a `FileResponse` handler for the three exact paths only; return 404 when there is no built shell. Do not add a wildcard SPA fallback.

The XML must contain only `https://highlinescout.com/` and the three specified methodology paths. Robots must include `Sitemap: https://highlinescout.com/sitemap.xml` and disallow the five API route prefixes.

- [ ] **Step 4: Complete tests with a patched temporary frontend directory**

Create `index.html` containing `<html>shell</html>` in `tmp_path`, monkeypatch the helper, assert all three paths return it, and assert `/unknown` remains 404.

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest tests/test_seo.py tests/test_api.py tests/test_integration.py -q`

Expected: PASS.

Commit: `git add highliner/server/app.py tests/test_seo.py && git commit -m "feat: serve SEO crawler routes"`

### Task 2: SEO model and localized methodology page

**Files:**
- Create: `frontend/src/lib/seo.ts`
- Create: `frontend/src/components/SeoHead.tsx`
- Create: `frontend/src/components/HowItWorksPage.tsx`
- Create: `frontend/src/components/HowItWorksPage.test.tsx`
- Modify: `frontend/src/lib/i18n/strings.ts`
- Modify: `frontend/src/lib/i18n/I18nProvider.tsx`
- Modify: `frontend/src/lib/i18n/i18n.test.tsx`

**Interfaces:**
- `seoForPath(pathname: string): SeoPage` returns typed `title`, `description`, `canonical`, `lang`, and `alternates` fields.
- `HowItWorksPage` uses `useI18n()` and renders generic-source methodology plus safety content.
- `I18nProvider` accepts `initialLang?: Lang` to make localized pages deterministic.

- [ ] **Step 1: Write failing component/unit tests**

```tsx
expect(seoForPath("/en/how-it-works")).toMatchObject({
  canonical: "https://highlinescout.com/en/how-it-works", lang: "en",
});
render(<I18nProvider initialLang="en"><HowItWorksPage /></I18nProvider>);
expect(screen.getByRole("heading", { name: /how it works/i })).toBeInTheDocument();
expect(screen.queryByText(/ICGC|MITECO/)).not.toBeInTheDocument();
```

- [ ] **Step 2: Verify tests fail**

Run: `npm test -- --run frontend/src/components/HowItWorksPage.test.tsx`

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement focused copy and metadata data**

Add identical-key-set translations for a methodology title, intro, three workflow stages, generic data statement, safety limitations, map link, and menu link. The English title uses “The smarter way to scout your next line”; the description says “potential highline spots to scout.”

`HowItWorksPage` uses semantic `<main>`, one `<h1>`, an ordered list of workflow stages, a clearly named safety section, and a normal `<a href="/">` map link. It must say anchors, terrain, access, permissions, and suitability need in-person assessment.

`seoForPath` uses `const ORIGIN = "https://highlinescout.com"`; the homepage returns English metadata and each methodology path has all three alternates plus `x-default` to English.

- [ ] **Step 4: Default the map and localized pages to the correct language**

Change `pickInitialLang()`’s fallback to `"en"`. `initialLang` overrides saved/browser language only when the public route supplies it; normal map behavior keeps saved/browser selection.

- [ ] **Step 5: Verify and commit**

Run: `npm test -- --run frontend/src/components/HowItWorksPage.test.tsx frontend/src/lib/i18n/i18n.test.tsx`

Expected: PASS.

Commit: `git add frontend/src/lib/seo.ts frontend/src/components/SeoHead.tsx frontend/src/components/HowItWorksPage.tsx frontend/src/components/HowItWorksPage.test.tsx frontend/src/lib/i18n/strings.ts frontend/src/lib/i18n/I18nProvider.tsx frontend/src/lib/i18n/i18n.test.tsx && git commit -m "feat: add localized methodology content"`

### Task 3: Route-aware document head and map navigation

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/NavMenu.tsx`
- Modify: `frontend/src/components/NavMenu.test.tsx`
- Create: `frontend/src/main.test.tsx`

**Interfaces:**
- `SeoHead` consumes `SeoPage` and writes a single title, description, canonical, Open Graph, Twitter, alternate, and JSON-LD set.
- `main.tsx` selects `HowItWorksPage` for only the three public paths; all other paths retain `App`.

- [ ] **Step 1: Write failing bootstrap tests**

```tsx
renderPublicApp("/");
expect(document.documentElement.lang).toBe("en");
expect(document.querySelector('link[rel="canonical"]')?.getAttribute("href"))
  .toBe("https://highlinescout.com/");
renderPublicApp("/ca/how-it-works");
expect(document.querySelectorAll('link[rel="alternate"][hreflang]').length).toBe(4);
```

- [ ] **Step 2: Verify the failing test**

Run: `npm test -- --run frontend/src/main.test.tsx frontend/src/components/NavMenu.test.tsx`

Expected: FAIL because the root-only bootstrap has no route metadata or menu item.

- [ ] **Step 3: Implement head and navigation**

In `main.tsx`, normalize `window.location.pathname`, call `seoForPath`, render `SeoHead`, then select the map or methodology component. `SeoHead` must identify nodes with stable attributes and replace existing values rather than append duplicates.

Use `WebApplication` JSON-LD with name `HighlineScout`, homepage URL, `applicationCategory: "TravelApplication"`, and publisher organization name `HighlineScout`; omit unsupported claims and `twitter:site`.

Set `frontend/index.html`’s static fallback title/description to the approved English copy. Add an ordinary-anchor “How it works” item to `NavMenu`, choosing its href from the current language; preserve the About dialog.

- [ ] **Step 4: Verify and commit**

Run: `npm test -- --run frontend/src/main.test.tsx frontend/src/components/NavMenu.test.tsx && npm run build`

Expected: PASS.

Commit: `git add frontend/index.html frontend/src/main.tsx frontend/src/components/NavMenu.tsx frontend/src/components/NavMenu.test.tsx frontend/src/main.test.tsx && git commit -m "feat: add SEO metadata and methodology navigation"`

### Task 4: Social image and end-to-end verification

**Files:**
- Create: `frontend/public/social-card.png`
- Modify: `frontend/src/lib/seo.ts`
- Modify: `frontend/src/main.test.tsx`

**Interfaces:**
- All public pages use `https://highlinescout.com/social-card.png` with 1200x630 dimensions and descriptive alt text.

- [ ] **Step 1: Create the visual asset**

Use the image-generation workflow with `frontend/src/assets/logo.svg` as reference. Produce a 1200x630 PNG with a deep forest-green/teal ground, the existing HighlineScout logo, and no real or implied verified line/location.

- [ ] **Step 2: Test and add social metadata**

```tsx
expect(document.querySelector('meta[property="og:image"]')?.getAttribute("content"))
  .toBe("https://highlinescout.com/social-card.png");
expect(document.querySelector('meta[name="twitter:card"]')?.getAttribute("content"))
  .toBe("summary_large_image");
```

Run: `npm test -- --run frontend/src/main.test.tsx && npm run build`

Expected: PASS and `frontend/dist/social-card.png` exists.

- [ ] **Step 3: Full verification and commit**

Run: `just test && just test-web && just check && just build-web`

Expected: PASS.

Commit: `git add frontend/public/social-card.png frontend/src/lib/seo.ts frontend/src/main.test.tsx && git commit -m "feat: add social sharing card"`

After deployment, submit `https://highlinescout.com/sitemap.xml` in Google Search Console, inspect its four URLs, and verify that `https://www.highlinescout.com` permanently redirects to the apex domain.
