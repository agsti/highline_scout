# Nav menu system (design handoff option 4a)

Replaces the nav's controls cluster (language segmented control + info button)
with a single menu button opening a dropdown panel. The panel is the extension
point for future entries (saved spots, settings, changelog) without crowding the
nav.

Source: `design_handoff_menu_system/README.md`, option 4a. Brand pill, filter
pill, zoom controls and density meter are out of scope and unchanged.

## Decisions that diverge from the handoff

The handoff was written against a codebase that does not exist yet in three
places. Resolved with the user:

1. **No account header row.** The handoff's header ("Entrar" / "Guarda tus
   zonas", tap → auth flow) assumes an auth system. This app has none: no
   session, no provider, no backend endpoint, no "saved zones" feature. Shipping
   the row would ship an affordance that does nothing. It is omitted. The panel
   keeps a clean top edge where the row slots in later — adding it is additive.
   The `signIn` and `saveYourZones` i18n keys are therefore not added.

2. **All breakpoints, not mobile-only.** The handoff scopes itself to mobile and
   defers desktop to option 4c. But `FloatingNav` renders one nav for both
   breakpoints, so honouring that literally means two nav code paths to keep in
   sync, and leaves Feedback/Seguridad unreachable on desktop. The menu replaces
   the pill everywhere. The component is named `NavMenu`, not the handoff's
   `MobileMenu`, to reflect this.

3. **Feedback is a visible coming-soon item.** Its bottom sheet is option 4b, out
   of scope. The user chose to render the item now rather than defer it. It is
   not a silent no-op: activating it swaps the row into an inline "coming soon"
   state, so it announces its own status instead of appearing broken.

## Tokens

Every colour in the handoff already exists as a CSS custom property. Use the
tokens; do not hardcode the hexes.

| Handoff | Token |
| --- | --- |
| deep primary `#114B45` | `--primary-deep` → `bg-primary-deep` / `text-primary-deep` |
| card `#FCFDFC` | `--card` |
| accent `#E6EFE9` | `--accent` |
| muted-foreground `#63807A` | `--muted-foreground` |
| hairline `#E3ECE6` | `--hairline` |
| foreground `#16302A` | `--foreground` |

Two shadows are new; add them to `tailwind.config.ts` `boxShadow`. They are close
to but not equal to the existing `pill` / `panel` shadows, and the handoff calls
its values final:

- `menu-button`: `0 2px 10px rgba(22,48,42,0.2)`
- `menu`: `0 12px 36px rgba(22,48,42,0.28)`

## Components

### `ui/popover.tsx` (new)

shadcn Radix Popover primitive, matching the existing `ui/dialog.tsx` house
style. Adds `@radix-ui/react-popover`; its transitive deps (dismissable-layer,
focus-scope, portal, popper, presence) are already installed via dialog/select,
so the install is small.

Popover, not `DropdownMenu`, deliberately: `DropdownMenu` imposes menu-item
semantics and roving tabindex, which fight the language segmented control in the
footer (three peer buttons with `aria-pressed`, none of which should close the
panel). Popover gives Escape, outside-click dismissal and focus return without
constraining the children.

### `NavMenu.tsx` (new)

Owns the button, scrim, panel, items and language footer.

- **Button** — 42px circle, `bg-primary-deep`, `rounded-full`,
  `shadow-menu-button`. lucide `Menu` icon, 16px, white, stroke 1.6; swaps to `X`
  while open. Sits in the nav row opposite the brand pill. `aria-label` from the
  new `menu` key; `aria-expanded` reflects state.
- **Scrim** — while open, a full-map overlay at `rgba(22,48,42,0.18)`, `z-[1100]`,
  tap to dismiss.
- **Panel** — `z-[1110]`, top 64px / right 12px, width 248px, `bg-card`,
  radius 16px, `shadow-menu`, `overflow-hidden`. Scale + fade from the top-right
  origin, ~150ms ease-out, via the `data-state` hooks Radix exposes and the
  `tailwindcss-animate` plugin already in the config.
- **Items** — container padding 6px. Each item is a flex row, gap 10px, padding
  11px 10px, radius 10px, 13px/600, `text-foreground`, `hover:bg-accent`; icon
  16px `text-muted-foreground`. All rows ≥44px hit height.
  - Enviar comentarios (`MessageSquarePlus`) → coming-soon state
  - Acerca de (`Info`) → about dialog
  - Seguridad (`ShieldAlert`) → safety dialog
- **Language footer** — padding 10px 14px, top border `border-hairline`,
  space-between. Label "Idioma" 11px/650 uppercase, letter-spacing 0.04em,
  `text-muted-foreground`, then the segmented switcher.

**Dismissal:** scrim tap, Escape, and selecting Acerca de / Seguridad. Changing
language does **not** close the panel — the handoff's "dismiss on item selection"
refers to the item list; the footer is a control, and closing the panel out from
under someone comparing languages would be hostile.

### `LanguageSwitcher.tsx` (modified)

Gains `variant?: "pill" | "segmented"`, defaulting to `pill`. `LANGS`, `setLang`
and the `SHORT`/`NAMES` maps are untouched — the variant only selects chrome, so
the switching logic stays in one place.

- `pill` — today's appearance. Still used by `SafetyDisclaimerDialog`.
- `segmented` — container `bg-accent`, radius 8px, padding 2px. Active segment
  `bg-card`, radius 6px, 11px/700, `text-primary-deep`, shadow
  `0 1px 3px rgba(22,48,42,0.12)`. Inactive transparent, 11px/600,
  `text-muted-foreground`.

### `AboutDialog.tsx` (rewritten) and `SafetyDialog.tsx` (new)

Today's `AboutDialog` is one dialog holding everything: safety disclaimer,
caveat, MITECO credit and privacy. The handoff splits the menu into two entries,
so the content splits to match.

- **`SafetyDialog`** takes the safety content unchanged: `disclaimerLead`,
  `disclaimerBody`, `disclaimerResponsibility`, `caveat`, `restrictionCredit`.
  Title from the new `safety` key. This is the handoff's "full existing caveat
  text + MITECO credit".
- **`AboutDialog`** keeps the `about` title and gets `aboutBody`, a data-credit
  line, and the existing `disclaimerPrivacy`.

Both reuse `ui/dialog.tsx` and its `z-[1210]`, so they layer above the menu.

## i18n

`language` ("Idioma") and `about` already exist and are reused — no duplicate
keys. New keys, all three of ca/es/en:

| Key | en |
| --- | --- |
| `menu` | "Menu" |
| `feedback` | "Send feedback" |
| `feedbackComingSoon` | "Coming soon" |
| `safety` | "Safety" |
| `aboutBody` | "Highline Scout helps you find spots." |
| `aboutData` | "Elevation data © ICGC. Protected-area data © MITECO." |

> **`aboutBody` is a deliberate placeholder.** The user will rewrite it. Do not
> polish it, and do not expand it into invented product voice.

## Wiring

`App.tsx` already owns `aboutOpen`; add `safetyOpen` beside it and render
`<SafetyDialog>` next to `<AboutDialog>`. `MapChrome` passes `onAbout` through
today; add `onSafety` alongside it. `FloatingNav` drops the controls pill and the
`Info` button and renders `<NavMenu onAbout onSafety />`.

## Testing

- `NavMenu.test.tsx` (new) — button opens the panel; scrim tap, Escape, and
  selecting Acerca de / Seguridad each close it; those two fire their callbacks;
  changing language leaves the panel open; the feedback item shows its
  coming-soon state.
- `SafetyDialog.test.tsx` (new) — asserts the caveat and the MITECO credit, so
  the move out of `AboutDialog` cannot silently drop them.
- `AboutDialog` test (in `FloatingNav.test.tsx`) — retarget from the safety
  assertions to the new About content.
- `FloatingNav.test.tsx` — the language group and info button are gone; assert
  the menu button instead.
- `LanguageSwitcher.test.tsx` — cover both variants; the existing assertions
  become the `pill` case.
