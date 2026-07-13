# BrandPill logo design

## Scope

Use `frontend/assets/logo.svg` as the only visible content of `BrandPill`.

## Rendering

`BrandPill` keeps its existing pill container, background, shadow, and responsive
padding. It renders the SVG through an image element sized to the pill rather
than showing the former `HS` badge or a separate text heading.

## Accessibility

The image has the alternative text `Highline Scout`, which is the BrandPill's
accessible name. No duplicate heading is rendered.

## Verification

Update the navigation test to assert the image is exposed with that accessible
name, then run the focused frontend test.
