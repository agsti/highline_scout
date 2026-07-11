# Tappable mobile filter card

## Problem

The collapsed mobile card now shows the applied filters and a restriction legend
(see `2026-07-11-mobile-collapsed-filter-card-design.md`), but two things about
it still read wrong:

- **It doesn't say what it is.** Dropping the `Highline Scout` title left the
  card with no label at all — just numbers and colour chips. Nothing tells you
  these are *filters*.
- **Only the button is tappable.** The card is a big touch target that mostly
  does nothing; you must hit the small `Filters` button in its corner. On a
  phone that is the wrong affordance — the card looks tappable, so it should be.

## Goal

The card announces itself as the filters card, and tapping it anywhere expands
the sheet. The dedicated `Filters` button goes away.

## Design

### Layout

```
┌──────────────────────────────────┐
│              ▁▁▁▁                │  grip (kept — reads as "drag/tap me")
│ ⚙ FILTERS                      ⌃ │  caption row + chevron
│ 20–150 m · exp ≥30 m             │  applied filters
│ ● ZEPA (Aus)  ● ZEC / LIC        │  legend (only when layers are on)
└──────────────────────────────────┘
```

- **Caption row:** the `SlidersHorizontal` icon plus `t("filters")`, small and
  muted — this is the "what am I" line. A `ChevronUp` sits at the right as the
  expand affordance.
- **Summary and legend rows:** unchanged from the previous design.

No new i18n strings. The caption reuses the existing `filters` key; the chevron
reuses `openControls`.

### Interaction

The card `<div>` takes an `onClick` that opens the sheet, plus `cursor-pointer`.
Tapping anywhere — caption, summary, legend, padding — expands it.

The **chevron is a real `<button>`**, wrapped in `SheetTrigger asChild`. This is
what keeps the card reachable without a pointer: a bare `onClick` on a `<div>`
cannot take focus, has no role, and cannot be activated by VoiceOver or
TalkBack. Since this card is the only route into the filters on mobile, losing
that would make the filters unreachable for those users — a regression from
today, where a real button exists. So:

- **Pointer:** the card's `onClick` fires. Tap anywhere.
- **Keyboard / screen reader:** tab to the chevron, which carries Radix's
  `aria-expanded` and the `openControls` label.

**The div's handler must be `onOpenChange(true)`, never a toggle.** Clicking the
chevron fires both the trigger and the div's `onClick` (the click bubbles), so
both paths must converge on "open" for the double-fire to be idempotent. A
toggle would cancel the trigger out and the chevron would appear dead.

### What does not change

`RestrictionLegend` is untouched: it stays outside any button, so its `<ul>` /
`<li>` markup remains valid and its tests remain as written. `App.tsx` is
untouched — this is entirely inside `MobileControlSheet`. The sheet's contents,
the desktop sidebar, and the `data-testid="mobile-summary-card"` all stay put.

### Rejected alternative

Making the whole card one `<button>` was considered and rejected. HTML forbids a
`<button>` from containing `<ul>` / `<li>` (a button may hold only phrasing
content), so it would have forced `RestrictionLegend` to be rewritten as
`<span>`s and its four unit tests re-queried — real churn on just-reviewed code,
to reach the same behaviour this design gets for free.

## Testing

- **`App.mobile.test.tsx`** — new test: clicking the card's *summary text* (not
  any button) opens the sheet. This is the behaviour being added and nothing
  currently covers it. The existing tests that query the trigger by
  `/open controls/i` keep working, because the chevron inherits that label.
- No new test file. `RestrictionLegend.test.tsx` needs no changes.
