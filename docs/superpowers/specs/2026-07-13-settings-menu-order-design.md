# Settings menu order and Safety dialog removal

## Scope

Reorder the settings menu to show restriction areas, language, feedback, and
about in that order. Remove the Safety action that is launched from this menu.
The first-visit safety disclaimer remains unchanged.

## Design

`NavMenu` will render its existing restriction-area controls first, followed by
the language selector. Its remaining action list will contain Feedback and
About, in that order. The Safety menu item and its icon import will be removed.

The app will no longer hold state for, import, or render `SafetyDialog`, and
the `onSafety` prop will be removed from `NavMenu` and its callers. The
`SafetyDialog` component and its dedicated test will be deleted because no
remaining feature uses them. `SafetyDisclaimerDialog` is intentionally outside
this change and continues to control the first-visit acknowledgement.

## Verification

Update the navigation-menu tests to prove the new rendered order and absence
of the Safety action, while retaining feedback, About, language, and
restriction-area interactions. Run the focused frontend tests and the frontend
type/build check appropriate to the repository scripts.
