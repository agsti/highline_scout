# Welcome Dialog Photo Design

## Goal

Make the welcome dialog immediately communicate highlining by adding the
provided Catalunya photograph and giving the product's main promise more visual
weight, while preserving the blocking safety gate and its translations.

## Image Asset

Use `/home/gus/Downloads/Highline Catalunya-A Noguero-18.jpg` as the source.
Create a roughly 2:1 panoramic crop that:

- keeps the highliner clearly visible, slightly right of center;
- retains enough of the line and forested valley to communicate scale;
- excludes the embedded lower-right watermark, as requested; and
- does not generate, remove, or otherwise alter scene content beyond cropping.

Save the web-ready result under `frontend/src/assets/` with a descriptive name.
The dialog image will have localized alternative text describing a person
highlining above a forested valley.

## Dialog Layout

Keep the existing logo and language switcher in the top row. Place the cropped
photograph directly beneath that row as a wide editorial image with restrained
rounded corners. Widen the desktop dialog modestly from `max-w-md` to
`max-w-xl`; on narrow screens it remains a single-column layout. Bound the
dialog height to the viewport and allow internal scrolling so the new image
does not hide the acknowledgement action on short screens.

Render the existing localized `disclaimerIntro` as the primary message below
the image, using larger semibold brand-green type. The three safety safeguards
remain quieter body text beneath it, and the existing acknowledgement button
remains the only way to close the gate. No safety copy or blocking behavior
changes.

## Accessibility and Localization

Add the image alternative-text key to all three `STRINGS` catalogs. Keep the
intro as one localized sentence rather than splitting translations into styled
fragments. The visual emphasis comes from styling the whole sentence, which
avoids unnatural word-order constraints across Catalan, Spanish, and English.

The modal retains its focus trap, inert background, body scroll lock, hidden
close control, and prevention of Escape and outside-click dismissal.

## Testing and Verification

Update the dialog component test to verify that:

- the cropped highlining image is present with localized alternative text;
- the intro is rendered as the emphasized primary message;
- all safety safeguards remain present; and
- acknowledgement and blocking interactions remain unchanged.

Run the focused dialog test, the frontend test suite, and the production
frontend build.
