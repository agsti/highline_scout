# Welcome Dialog Photo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the supplied highlining photograph to the welcome dialog and promote the localized product promise into its primary message.

**Architecture:** A cropped, optimized image lives beside the existing frontend assets and is imported by `SafetyDisclaimerDialog`. The component remains the same blocking Radix dialog, with responsive overflow protection and a localized image description added through the existing flat i18n catalogs.

**Tech Stack:** React, TypeScript, Tailwind CSS, Radix Dialog, Vitest, Testing Library, Vite, built-in image editing.

## Global Constraints

- Use `/home/gus/Downloads/Highline Catalunya-A Noguero-18.jpg` as the only image source.
- The crop is roughly 2:1, keeps the highliner slightly right of center, retains the line and valley, and excludes the lower-right watermark.
- Do not alter scene content beyond cropping and web optimization.
- Keep Catalan, Spanish, and English catalogs at exact key parity.
- Preserve the modal focus trap, inert background, body scroll lock, hidden close control, and prevention of Escape and outside-click dismissal.
- Keep the acknowledgement button as the only close path.

---

### Task 1: Produce the welcome image asset

**Files:**
- Source: `/home/gus/Downloads/Highline Catalunya-A Noguero-18.jpg`
- Create: `frontend/src/assets/welcome-highline.webp`

**Interfaces:**
- Consumes: the supplied JPEG source.
- Produces: the static asset imported as `highlinePhoto` by `SafetyDisclaimerDialog`.

- [ ] **Step 1: Create the crop with the image-editing tool**

Use the source image as the edit target with this exact instruction:

```text
Use case: precise-object-edit
Asset type: welcome-dialog editorial photograph
Primary request: crop this exact photograph to a wide 2:1 composition.
Composition/framing: keep the highliner clearly visible and slightly right of center; retain the highline running across the frame and enough forested valley to communicate height and scale.
Constraints: crop only; exclude the embedded lower-right ANDREU NOGUERO watermark; preserve every remaining pixel and all scene content without generative additions, removals, retouching, relighting, recoloring, or text.
Avoid: invented scenery, changed person, changed line, watermark, captions, logos, borders.
```

Copy the selected result to `frontend/src/assets/welcome-highline.webp` without overwriting any existing asset.

- [ ] **Step 2: Validate the generated asset**

Run:

```bash
file frontend/src/assets/welcome-highline.webp
identify -format '%w %h' frontend/src/assets/welcome-highline.webp
```

Expected: a valid WebP whose width is approximately twice its height. Inspect it at original detail and confirm the person, line, and valley match the source and no watermark is visible.

- [ ] **Step 3: Commit the asset**

```bash
git add frontend/src/assets/welcome-highline.webp
git commit -m "feat: add welcome highline photo"
```

---

### Task 2: Integrate the image and emphasized promise

**Files:**
- Modify: `frontend/src/components/SafetyDisclaimerDialog.test.tsx`
- Modify: `frontend/src/components/SafetyDisclaimerDialog.tsx`
- Modify: `frontend/src/lib/i18n/strings.ts`

**Interfaces:**
- Consumes: `highlinePhoto: string` from `@/assets/welcome-highline.webp` and `t("disclaimerImageAlt")` from the i18n context.
- Produces: a responsive welcome dialog containing the editorial image and emphasized `disclaimerIntro`.

- [ ] **Step 1: Write the failing component assertions**

In the existing English content test, add these assertions after obtaining `dialog`:

```tsx
const photo = screen.getByRole("img", {
  name: "A person highlining above a forested valley",
});
expect(photo).toHaveAttribute("src", expect.stringContaining("welcome-highline"));

const intro = screen.getByText(
  "HighlineScout helps you find your next potential highline spot.",
);
expect(intro).toHaveClass("text-lg", "font-semibold", "text-primary-deep");
```

Keep the existing logo, heading absence, safeguard, interaction, and body-lock assertions.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
cd frontend && npm test -- --run src/components/SafetyDisclaimerDialog.test.tsx
```

Expected: FAIL because the localized photo and emphasized intro do not yet exist.

- [ ] **Step 3: Add localized alternative text**

Add `disclaimerImageAlt` beside `disclaimerIntro` in every catalog:

```ts
// ca
disclaimerImageAlt: "Una persona fent highline sobre una vall boscosa.",

// es
disclaimerImageAlt: "Una persona haciendo highline sobre un valle boscoso.",

// en
disclaimerImageAlt: "A person highlining above a forested valley",
```

- [ ] **Step 4: Implement the responsive editorial layout**

Import the asset:

```tsx
import highlinePhoto from "@/assets/welcome-highline.webp";
```

Change the dialog content class to:

```tsx
className="z-[1210] max-h-[calc(100dvh-2rem)] max-w-xl overflow-y-auto"
```

Insert this image immediately after the logo/language row:

```tsx
<img
  src={highlinePhoto}
  alt={t("disclaimerImageAlt")}
  className="aspect-[2/1] w-full rounded-md object-cover"
/>
```

Separate the intro from the safeguard body and emphasize it:

```tsx
<p className="text-lg font-semibold leading-snug text-primary-deep">
  {t("disclaimerIntro")}
</p>
<ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
  <li>{t("disclaimerBeginner")}</li>
  <li>{t("disclaimerAnchors")}</li>
  <li>{t("disclaimerLimitations")}</li>
</ul>
```

Do not change the `Dialog`, dismissal prevention handlers, logo row, or button.

- [ ] **Step 5: Run focused tests and catalog parity coverage**

Run:

```bash
cd frontend && npm test -- --run src/components/SafetyDisclaimerDialog.test.tsx src/lib/i18n/i18n.test.tsx
```

Expected: both test files pass.

- [ ] **Step 6: Run frontend verification**

Run:

```bash
just test-web
just build-web
```

Expected: the complete Vitest suite passes and the Vite production build succeeds.

- [ ] **Step 7: Inspect the rendered dialog**

Run the existing development frontend, open the welcome dialog at desktop and narrow mobile viewport widths, and confirm the image subject is readable, the button remains reachable, and internal scrolling only appears when the viewport is short.

- [ ] **Step 8: Commit the integration**

```bash
git add frontend/src/components/SafetyDisclaimerDialog.tsx \
  frontend/src/components/SafetyDisclaimerDialog.test.tsx \
  frontend/src/lib/i18n/strings.ts
git commit -m "feat: add photo to welcome dialog"
```
