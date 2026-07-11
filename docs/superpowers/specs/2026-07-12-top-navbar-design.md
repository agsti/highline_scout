# Top navbar — design

## Goal

Give the web app a persistent top navbar on both mobile and desktop, carrying the
product brand and the language switcher. Today the brand (`Highline Scout`) lives in
the desktop sidebar only, and the language switcher is duplicated in the desktop
sidebar and the mobile control sheet. The navbar becomes the single home for both.

## Scope

In scope: brand + language switcher in a top bar; removing the now-duplicated copies
from the sidebar and the mobile sheet.

Out of scope: moving the sidebar collapse control into the navbar; an about/safety
link; navigation links (the app is a single page with no router).

## Layout

The navbar is a solid bar in normal flow that pushes content down — it does not float
over the map. This costs ~56px of map height and in exchange nothing is ever hidden
behind it, and the sidebar reads as a clean column under the bar.

```
DESKTOP                                    MOBILE
┌────────────────────────────────────┐     ┌──────────────────────────┐
│ Highline Scout        [CA][ES][EN] │     │ Highline Scout  CA·ES·EN │
├───────────┬────────────────────────┤     ├──────────────────────────┤
│ sidebar   │                        │     │                          │
│ filters   │         MAP            │     │           MAP            │
│ statuses  │                        │     │  ┌────────────────────┐  │
│ layers    │                        │     │  │ ▬  Filters         │  │
└───────────┴────────────────────────┘     └──┴────────────────────┴──┘
```

## Components

### `NavBar.tsx` (new)

A `<header>` with the `Highline Scout` `<h1>` on the left and the language switcher on
the right: `h-14`, `border-b`, `bg-card`, `shrink-0`. One component at every
breakpoint; the only responsive treatment is tighter horizontal padding on small
screens. No new i18n strings — the brand is a proper noun and the switcher already
localizes its own `aria-label`.

### `AppShell.tsx` (restructured)

The root becomes `flex h-dvh flex-col`: the navbar first, then a
`relative flex-1 overflow-hidden` region holding exactly what the root holds today —
the absolutely-positioned sidebar, the collapse tab, `<main>`, and the mobile controls.

Because those children are absolutely positioned, re-parenting them into that region is
the whole change: they anchor to the region instead of the viewport, so the sidebar and
its collapse tab land below the navbar with no edits to their own classes, and `<main>`
shrinks so Leaflet gets a shorter container. The mobile sheet is `fixed`, so it stays
pinned to the viewport bottom regardless.

### `DesktopSidebar.tsx`

Drop the `<h1>Highline Scout</h1>` block and the `mt-auto border-t pt-4` footer holding
the `LanguageSwitcher`.

### `MobileControlSheet.tsx`

Drop the `<LanguageSwitcher compact />` from the sheet body.

### `LanguageSwitcher.tsx`

Callers after the removals are the navbar and `SafetyDisclaimerDialog` (which keeps its
switcher — it is shown before the app is usable, so language must be selectable from
inside it). Both want the label-less form, so `compact` has one possible value: remove
the prop and always render the button group without the "Language" heading, keeping
`aria-label={t("language")}` on the group for screen readers.

## Result

Once the safety disclaimer is dismissed, exactly one language control is on screen in
either layout, and the brand is visible on mobile for the first time.

## Testing

- `AppShell.test.tsx`: the navbar renders the brand and the three language buttons.
- A guard that, **after the safety disclaimer is accepted**, the app renders only one
  set of language buttons — so the sidebar/sheet copies cannot come back by accident.
  The disclaimer keeps its own switcher while open, so the guard must dismiss it first.
- Existing AppShell, App, and i18n tests must pass unchanged.
