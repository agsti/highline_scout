# Newsletter signup modal

## Goal

After the first-run welcome dialog, offer the visitor a one-field newsletter
signup. Store subscribers in **MailerLite** (a real mailing list we can send
monthly updates from), submitted through the existing Python backend so the API
key stays server-side. Keep the frontend's cookieless/anonymous PostHog posture
intact — PostHog records only that a signup happened, never the email.

## Copy

- Heading: **"Want to stay in the loop?"**
- Subtext: **"Only updates — we won't message more than once a month."**
- Primary button: **"Subscribe"**
- Secondary action: **"Don't show again"**

All strings localized in `frontend/src/lib/i18n/strings.ts` for `ca`, `es`, `en`
(the existing three languages), following the current `STRINGS` shape.

## Behavior

- The welcome modal (`SafetyDisclaimerDialog`) has **no persistence** and shows
  on every load. The newsletter modal opens **immediately after** the user
  clicks "I understand" — i.e. the welcome `onAccept` closes the welcome dialog
  and opens the newsletter dialog.
- Unlike the welcome gate, the newsletter modal is **dismissable**: X button,
  Escape, and outside-click all close it.
- A permanent `localStorage` flag `newsletterPrompted` suppresses the modal on
  all future loads. It is set by **two** actions only:
  1. a **successful subscribe**, and
  2. clicking **"Don't show again"**.
- A plain close (X / Escape / outside-click) does **not** set the flag; it only
  hides the modal for the current session. Because the modal is triggered once
  per welcome-accept and the welcome dialog itself shows once per load, this
  naturally means "show once per session until the visitor subscribes or opts
  out permanently".

### Dialog states

- **idle** — email input + Subscribe + "Don't show again".
- **sending** — Subscribe disabled, shows a sending label.
- **success** — replaces the form with a confirmation message:
  *"Almost there — check your inbox to confirm."* (worded for MailerLite double
  opt-in). Sets `newsletterPrompted`. Emits `capture("newsletter_signup")` —
  **event only, no email property** — preserving the anonymous posture.
- **error** — inline message *"Couldn't subscribe. Try again."*; form stays so
  the visitor can retry.

Email validation: `type="email"` input; Subscribe disabled until the field is
non-empty. Server does the authoritative validation.

## Frontend components

- **`frontend/src/components/NewsletterDialog.tsx`** — new component. Mirrors
  `SafetyDisclaimerDialog` styling and `FeedbackDialog`'s form/submit/`capture`
  pattern. Props: `open: boolean`, `onClose: () => void`, `onDismissForever:
  () => void` (or a single `onOpenChange` plus an explicit dismiss callback —
  implementer's choice as long as the two permanent-flag paths are distinct
  from a plain close).
- **`frontend/src/App.tsx`** — wire it in:
  - Add state to track whether the newsletter modal is open.
  - On welcome `onAccept`: close the welcome dialog and, if
    `newsletterPrompted` is not set in `localStorage`, open the newsletter
    modal.
  - Guard `localStorage` reads/writes in `try/catch` (private mode), matching
    the existing `pickInitialRestrictionAreaMode` pattern.
  - Render `<NewsletterDialog>` alongside the other dialogs.

## Backend

Mirrors the `/feedback` implementation exactly.

- **`highliner/server/services/subscribe.py`**
  - `add_subscriber(settings, email)`:
    - Raise `SubscribeUnavailable` if `settings.mailerlite_api_key` is unset.
    - `POST https://connect.mailerlite.com/api/subscribers` with headers
      `Authorization: Bearer <key>`, `Content-Type: application/json`,
      `Accept: application/json`; body `{"email": email}` plus
      `"groups": [settings.mailerlite_group_id]` when the group id is set.
    - `timeout=10`; on `requests.RequestException` or non-2xx raise
      `SubscribeDeliveryError`.
  - Exceptions `SubscribeUnavailable`, `SubscribeDeliveryError` mirror the
    feedback ones.
  - Double opt-in is a MailerLite **account setting**, not code: when enabled,
    this call creates an `unconfirmed` subscriber and MailerLite sends the
    confirmation email itself.
- **`highliner/server/router/subscribe.py`**
  - `SubscribeRequest(BaseModel)` with `email: str`, validated like
    `feedback.reply_email` (`len <= 254` and contains `"@"`).
  - `POST /subscribe`, `status_code=201`. Reuse the feedback IP rate-limit
    pattern (5 attempts / 3600 s per client IP; its own `_ATTEMPTS` dict).
  - Map `SubscribeUnavailable` → `HTTPException(503)`,
    `SubscribeDeliveryError` → `HTTPException(502)`.
  - Returns `{"status": "subscribed"}`.
- **`highliner/server/app.py`** — add `subscribe` to the router imports and the
  `include_router` loop.
- **`highliner/core/config.py`** — add to `Settings`, next to the Resend fields:
  - `mailerlite_api_key: str | None = None`
  - `mailerlite_group_id: str | None = None`
  Both optional; absent means disabled (dev machines send nothing). Overridable
  via `HIGHLINER_MAILERLITE_API_KEY` / `HIGHLINER_MAILERLITE_GROUP_ID`.

## Testing

- **Backend** (mirror the feedback router tests, mocking `requests.post`):
  - valid email → 201 and MailerLite called with the right URL/headers/body;
  - malformed email → 422;
  - not configured (no api key) → 503;
  - MailerLite error / timeout → 502;
  - over rate limit → 429.
- **Frontend** (mirror `SafetyDisclaimerDialog.test.tsx` / feedback tests):
  - modal renders after welcome accept when `newsletterPrompted` is unset;
  - does **not** render when the flag is already set;
  - successful submit shows the confirm message, sets the flag, and fires
    `capture("newsletter_signup")` with no email;
  - "Don't show again" sets the flag and closes without subscribing;
  - error response keeps the form and shows the error message.

## Out of scope / operator setup (not code)

- Create the MailerLite account, generate an API key, optionally create a group
  for this list, enable **double opt-in**, and set
  `HIGHLINER_MAILERLITE_API_KEY` (and optionally `HIGHLINER_MAILERLITE_GROUP_ID`)
  in the deploy environment.
- Composing and scheduling the actual monthly emails happens in the MailerLite
  dashboard.
