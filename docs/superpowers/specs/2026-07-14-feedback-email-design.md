# Feedback email design

## Goal

Replace the menu's placeholder feedback action with a localized in-app form
that delivers user feedback to the maintainer by email through Resend.

## User experience

Selecting **Send feedback** closes the navigation menu and opens a dialog. The
dialog contains a compact topic selector, a required free-text message, and an
optional reply-email address. It explains that the reply address is used only
to respond to that message.

The submit control is unavailable until the message contains non-whitespace
text. During delivery it prevents duplicate submissions. On success, the form
is replaced by a confirmation and close action. On failure, it keeps the draft
and explains that delivery failed so the user can retry.

All copy is available in Catalan, Spanish, and English and follows the
existing dialog and i18n conventions.

## Delivery architecture

The browser sends a JSON `POST /feedback` request to the FastAPI application.
The endpoint validates the payload, applies an in-memory per-IP rate limit, and
sends a formatted plain-text email with Resend. No submission is persisted by
the application once the delivery attempt completes.

Deployment supplies these server-only settings:

- `HIGHLINER_RESEND_API_KEY`
- `HIGHLINER_FEEDBACK_TO`
- `HIGHLINER_FEEDBACK_FROM`

When feedback delivery is not configured, the endpoint returns a service
unavailable response and the frontend keeps the user's message for a later
retry. The API must not expose Resend details, credentials, or provider error
messages.

## Privacy and telemetry

Feedback text and reply addresses are never sent to PostHog. After a successful
delivery only, the frontend captures the existing anonymous analytics event
`feedback_submitted` with the selected topic. The form's privacy copy makes the
optional reply-email use explicit.

## Validation and abuse controls

The server accepts a small fixed topic set, a non-empty message with a bounded
length, and an optional syntactically valid email address with a bounded length.
It rate-limits by client IP using a process-local fixed window. This best-effort
limit resets across deploys and processes; reverse-proxy rate limiting remains
an optional production hardening layer.

## Tests

- Frontend dialog tests cover opening from the menu, required-message state,
  successful submission, preserved draft on failure, and localized strings.
- API tests cover valid delivery through a mocked Resend boundary, validation,
  configuration absence, and rate limiting.
- A narrow unit test verifies the Resend request format without using real
  credentials or network access.
