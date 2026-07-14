# Welcome Modal Logo Design

## Goal

Use the existing HighlineScout logo in the first-run safety disclaimer without
repeating the product name as a text title.

## Design

The top row of `SafetyDisclaimerDialog` will place the logo on the left and the
existing language switcher on the right. The `disclaimerTitle` heading will be
removed because the logo already identifies the product. The safety
introduction, safeguards, and acknowledgement action remain unchanged.

The SVG will be rendered as an image with concise alternative text and a fixed,
responsive visual height so it remains legible without dominating the modal.

## Testing

The dialog test will verify that the branded image is present and that the
redundant title heading is absent. Existing interaction and accessibility tests
remain the regression coverage for the blocking gate.
