# Favicon Design

## Goal

Use the supplied HighlineScout favicon artwork for browser tabs and Apple home-screen shortcuts.

## Scope

Extract only the three requested files from `Webapp icon design request.zip` into `frontend/public/`:

- `favicon.svg`
- `favicon-32.png`
- `favicon-180.png`

Add the corresponding root-relative icon links to `frontend/index.html`:

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="icon" href="/favicon-32.png" sizes="32x32" />
<link rel="apple-touch-icon" href="/favicon-180.png" />
```

## Behavior and Verification

Vite copies `frontend/public/` files to the production build root, so the root-relative links resolve in development and production. The frontend production build must succeed and include all three assets with these links in `dist/index.html`.

No other logo exports or application behavior change.
