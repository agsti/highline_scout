# Desktop Restriction Definitions

## Goal

Make restriction controls immediately available whenever the desktop filters pane is expanded, while keeping the pane compact as definitions grow.

## Desktop interaction

- Replace the collapsible restrictions footer with a permanently visible section beneath the filters and statuses.
- Keep the **Restrictions** heading, but remove its summary color swatches and disclosure chevron.
- Render each restriction as a compact row containing its checkbox, color marker, translated label, and a question-mark button.
- Do not render a selected restriction's definition inline.
- Clicking a question-mark button opens a separate definition card immediately to the right of the filters card. Align the top of this card with the top of the restrictions section.
- The definition card contains the translated restriction label and its full translated tooltip text, preserving the existing highlighted warning phrase.
- At most one definition card is open. Clicking another question mark replaces its content. Clicking the active question mark, clicking outside both cards, or collapsing the filters pane closes it.
- Question-mark buttons expose translated, restriction-specific accessible labels and their expanded state. The definition card is associated with its active button.

## Scope

The mobile control sheet and map restriction behavior remain unchanged. Existing restriction selection, analytics, localization sources, and map legend behavior also remain unchanged.

## Testing

Component tests will verify that restrictions are visible without a disclosure action, the old swatches and nested disclosure are absent, definitions are absent inline, only one definition card opens at once, and the supported dismissal actions close it. Tests will also check the relevant accessible expanded state and labels.
