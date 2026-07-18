# Welcome Country Selector Design

## Goal

Let first-time visitors choose the country they want to explore before entering
the map. The welcome dialog's choice must immediately become the active country,
persist as the visitor's manual preference, and remain editable from the
navigation menu afterward.

## Component Design

Extract the existing labeled country select from `NavMenu` into a reusable
`CountrySelect` component. It accepts the available `CountryEntry` catalog, the
active country id, the country-change callback, and a unique control id. Both
the welcome dialog and navigation menu use this component so their labels,
options, loading behavior, and styling stay consistent.

The unique control id prevents duplicate DOM ids while the blocking welcome
dialog and the background navigation are mounted together. The select is
disabled while the country catalog is empty, matching the current navigation
behavior.

## Dialog Layout and Data Flow

Place the country selector between the safety list and the acknowledgement
button. This makes country selection the final setup step before entering the
map without competing with the logo, language switcher, or editorial image.

`App` continues to own the country catalog and active-country state. It passes
`countries`, `country`, and the existing `handleCountryChange` callback into
`SafetyDisclaimerDialog`. A modal selection therefore follows the same path as
a navigation selection: it marks the choice as manual, saves it to local
storage, updates the active country, clears stale restriction metadata, and
causes the map to use the selected country's bounds and resources. Accepting
the disclaimer only closes the gate; it does not perform a separate country
commit.

Country labels remain the existing country ids returned by the catalog. No new
translation keys or analytics events are introduced.

## Accessibility and Interaction

The shared control keeps the localized `country` label and accessible select
name. The modal retains its focus trap, inert background, body scroll lock,
hidden close control, and prevention of Escape and outside-click dismissal.
The acknowledgement button remains the only way to close the welcome gate.

## Testing and Verification

Add focused component coverage proving that the welcome dialog:

- renders the active country and all available country options;
- calls the supplied country-change callback when an option is chosen; and
- disables the selector while the catalog is empty.

Add App-level coverage proving that a country chosen from the welcome dialog
uses the existing persistence handler and updates the country passed to the
map. Keep the existing disclaimer interaction, accessibility, localization,
and country auto-detection tests green.

Run the focused dialog and App tests, the complete frontend test suite, and the
production frontend build.
