# Newsletter Signup Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After the welcome dialog, offer a one-field newsletter signup that stores subscribers in MailerLite via the Python backend, keeping PostHog anonymous.

**Architecture:** A new `/subscribe` FastAPI endpoint mirrors the existing `/feedback` endpoint (validated Pydantic payload, IP rate-limit, a service module that POSTs to an external API via `requests`, credentials in `config.Settings`). A new dismissable React dialog opens right after the welcome gate and POSTs the email to `/subscribe`; a `localStorage` flag suppresses it once subscribed or explicitly opted out.

**Tech Stack:** Python 3.12, FastAPI, pydantic, `requests` (backend); React + TypeScript, Radix dialog primitive, vitest + testing-library (frontend). Tooling via `uv` and `npm`.

## Global Constraints

- Backend tests run with `uv run pytest`; frontend tests with `cd frontend && npm test` (vitest).
- MailerLite credentials are **optional** settings (absent → feature disabled), overridable via `HIGHLINER_MAILERLITE_API_KEY` / `HIGHLINER_MAILERLITE_GROUP_ID`.
- Email validation rule (mirrors `feedback.reply_email`): `len(value) <= 254` and `"@" in value`.
- Localized strings exist for exactly three languages: `ca`, `es`, `en`. `StringKey = keyof typeof STRINGS.ca`, so **every new key must be added to all three** language blocks with identical key names.
- PostHog stays anonymous: emit `capture("newsletter_signup")` with **no email property**; never call `identify()`.
- MailerLite endpoint: `POST https://connect.mailerlite.com/api/subscribers`, headers `Authorization: Bearer <key>`, `Content-Type: application/json`, `Accept: application/json`, `timeout=10`.
- Copy (English): heading "Want to stay in the loop?", subtext "Only updates — we won't message more than once a month.", button "Subscribe", secondary "Don't show again", success "Almost there — check your inbox to confirm.", error "Couldn't subscribe. Try again."
- `localStorage` flag key: `newsletterPrompted`. Reads/writes wrapped in `try/catch` (private mode), matching `pickInitialRestrictionAreaMode` in `App.tsx`.

---

### Task 1: Backend config + MailerLite service

**Files:**
- Modify: `highliner/core/config.py:74-76` (add MailerLite settings after the Resend fields)
- Create: `highliner/server/services/subscribe.py`
- Test: `tests/highliner/server/services/test_subscribe.py`

**Interfaces:**
- Consumes: `highliner.core.config.Settings`.
- Produces:
  - `Settings.mailerlite_api_key: str | None`, `Settings.mailerlite_group_id: str | None`
  - `add_subscriber(settings: config.Settings, email: str) -> None`
  - `class SubscribeUnavailable(Exception)`, `class SubscribeDeliveryError(Exception)`

- [ ] **Step 1: Add the settings fields**

In `highliner/core/config.py`, inside `class Settings`, immediately after the `feedback_from` line (currently `highliner/core/config.py:76`), add:

```python
    mailerlite_api_key: str | None = None
    mailerlite_group_id: str | None = None
```

- [ ] **Step 2: Write the failing service tests**

Create `tests/highliner/server/services/test_subscribe.py`:

```python
import pytest

from highliner.core.config import Settings
from highliner.server.services.subscribe import (
    SubscribeDeliveryError,
    SubscribeUnavailable,
    add_subscriber,
)


class _Response:
    def raise_for_status(self) -> None:
        pass


def test_add_subscriber_posts_email_to_mailerlite(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> _Response:
        seen["url"] = url
        seen.update(kwargs)
        return _Response()

    monkeypatch.setattr(
        "highliner.server.services.subscribe.requests.post", post)

    add_subscriber(
        Settings(mailerlite_api_key="ml_test", mailerlite_group_id="42"),
        "rigger@example.com",
    )

    assert seen["url"] == "https://connect.mailerlite.com/api/subscribers"
    assert seen["headers"] == {
        "Authorization": "Bearer ml_test",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert seen["json"] == {"email": "rigger@example.com", "groups": ["42"]}
    assert seen["timeout"] == 10


def test_add_subscriber_omits_groups_when_no_group_id(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> _Response:
        seen.update(kwargs)
        return _Response()

    monkeypatch.setattr(
        "highliner.server.services.subscribe.requests.post", post)

    add_subscriber(Settings(mailerlite_api_key="ml_test"), "a@b.com")

    assert seen["json"] == {"email": "a@b.com"}


def test_add_subscriber_raises_unavailable_without_api_key() -> None:
    with pytest.raises(SubscribeUnavailable):
        add_subscriber(Settings(), "a@b.com")


def test_add_subscriber_wraps_request_errors(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def post(url: str, **kwargs: object) -> _Response:
        raise requests.RequestException("boom")

    monkeypatch.setattr(
        "highliner.server.services.subscribe.requests.post", post)

    with pytest.raises(SubscribeDeliveryError):
        add_subscriber(Settings(mailerlite_api_key="ml_test"), "a@b.com")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/server/services/test_subscribe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.server.services.subscribe'`

- [ ] **Step 4: Implement the service**

Create `highliner/server/services/subscribe.py`:

```python
"""Newsletter subscription through MailerLite."""

import requests

from highliner.core import config

_MAILERLITE_URL = "https://connect.mailerlite.com/api/subscribers"


class SubscribeUnavailable(Exception):
    """Newsletter subscription has not been configured."""


class SubscribeDeliveryError(Exception):
    """MailerLite did not accept the subscriber."""


def add_subscriber(settings: config.Settings, email: str) -> None:
    """Add one email to the MailerLite list (double opt-in handled by MailerLite)."""
    if not settings.mailerlite_api_key:
        raise SubscribeUnavailable
    payload: dict[str, object] = {"email": email}
    if settings.mailerlite_group_id:
        payload["groups"] = [settings.mailerlite_group_id]
    try:
        response = requests.post(
            _MAILERLITE_URL,
            headers={
                "Authorization": f"Bearer {settings.mailerlite_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise SubscribeDeliveryError from error
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/highliner/server/services/test_subscribe.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add highliner/core/config.py highliner/server/services/subscribe.py tests/highliner/server/services/test_subscribe.py
git commit -m "feat(backend): add MailerLite subscribe service"
```

---

### Task 2: Backend /subscribe endpoint

**Files:**
- Create: `highliner/server/router/subscribe.py`
- Modify: `highliner/server/app.py:21-30` (router imports) and `highliner/server/app.py:185-187` (include_router loop)
- Test: `tests/highliner/server/router/test_subscribe.py`

**Interfaces:**
- Consumes: `add_subscriber`, `SubscribeUnavailable`, `SubscribeDeliveryError` from Task 1; `config.settings`.
- Produces: `POST /subscribe` returning `{"status": "subscribed"}` (201); `router` (FastAPI `APIRouter`).

- [ ] **Step 1: Write the failing router tests**

Create `tests/highliner/server/router/test_subscribe.py`:

```python
import pytest
from fastapi.testclient import TestClient

from highliner.server.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_subscribe_accepts_a_valid_email(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "highliner.server.router.subscribe.add_subscriber",
        lambda settings, email: calls.append(email),
    )

    response = client.post("/subscribe", json={"email": "a@b.com"})

    assert response.status_code == 201
    assert response.json() == {"status": "subscribed"}
    assert calls == ["a@b.com"]


def test_subscribe_rejects_a_malformed_email(client: TestClient) -> None:
    response = client.post("/subscribe", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_subscribe_returns_503_when_not_configured(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.server.services.subscribe import SubscribeUnavailable

    def boom(settings: object, email: str) -> None:
        raise SubscribeUnavailable

    monkeypatch.setattr(
        "highliner.server.router.subscribe.add_subscriber", boom)

    response = client.post("/subscribe", json={"email": "a@b.com"})
    assert response.status_code == 503


def test_subscribe_returns_502_on_delivery_error(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.server.services.subscribe import SubscribeDeliveryError

    def boom(settings: object, email: str) -> None:
        raise SubscribeDeliveryError

    monkeypatch.setattr(
        "highliner.server.router.subscribe.add_subscriber", boom)

    response = client.post("/subscribe", json={"email": "a@b.com"})
    assert response.status_code == 502


def test_subscribe_rate_limits_after_five_attempts(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "highliner.server.router.subscribe.add_subscriber",
        lambda settings, email: None,
    )

    for _ in range(5):
        assert client.post("/subscribe", json={"email": "a@b.com"}).status_code == 201
    assert client.post("/subscribe", json={"email": "a@b.com"}).status_code == 429
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/server/router/test_subscribe.py -v`
Expected: FAIL (404 on POST /subscribe — route not registered yet, and the monkeypatch target module does not exist)

- [ ] **Step 3: Implement the router**

Create `highliner/server/router/subscribe.py`:

```python
"""Public newsletter subscription endpoint."""

from collections import defaultdict
from time import monotonic

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from highliner.core import config
from highliner.server.services.subscribe import (
    SubscribeDeliveryError,
    SubscribeUnavailable,
    add_subscriber,
)

router = APIRouter()
_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 3600
_MAX_ATTEMPTS = 5


class SubscribeRequest(BaseModel):
    """Validated public payload carrying only the email to subscribe."""

    email: str

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        if len(value) > 254 or "@" not in value:
            raise ValueError("email must be valid")
        return value


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(request: Request, payload: SubscribeRequest) -> dict[str, str]:
    """Validate, rate limit, and forward one newsletter subscription."""
    _enforce_rate_limit(request.client.host if request.client else "unknown")
    try:
        add_subscriber(config.settings, payload.email)
    except SubscribeUnavailable as error:
        raise HTTPException(503, "subscription is not configured") from error
    except SubscribeDeliveryError as error:
        raise HTTPException(502, "could not subscribe; try again") from error
    return {"status": "subscribed"}


def _enforce_rate_limit(ip: str) -> None:
    now = monotonic()
    attempts = [time for time in _ATTEMPTS[ip] if now - time < _WINDOW_SECONDS]
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(429, "too many subscription attempts; try later")
    attempts.append(now)
    _ATTEMPTS[ip] = attempts
```

- [ ] **Step 4: Register the router in app.py**

In `highliner/server/app.py`, add `subscribe` to the router import block (currently `highliner/server/app.py:21-30`) so it reads:

```python
from highliner.server.router import (
    anchors,
    countries,
    density,
    feedback,
    health,
    regions,
    restrictions,
    subscribe,
    zones,
)
```

And add `subscribe` to the `include_router` loop (currently `highliner/server/app.py:185-186`):

```python
    for module in (health, countries, regions, zones, anchors, density,
                   restrictions, feedback, subscribe):
        app.include_router(module.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/highliner/server/router/test_subscribe.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Run the full backend suite + lint/type gates**

Run: `uv run pytest tests/highliner/server -q && just lint && just typecheck`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add highliner/server/router/subscribe.py highliner/server/app.py tests/highliner/server/router/test_subscribe.py
git commit -m "feat(backend): add /subscribe newsletter endpoint"
```

---

### Task 3: Newsletter dialog component + i18n strings

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (add 8 keys to each of the `ca`, `es`, `en` blocks)
- Create: `frontend/src/components/NewsletterDialog.tsx`
- Test: `frontend/src/components/NewsletterDialog.test.tsx`

**Interfaces:**
- Consumes: `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle` from `@/components/ui/dialog`; `Button` from `@/components/ui/button`; `useI18n` from `@/lib/i18n`; `capture` from `@/lib/analytics`.
- Produces: `NewsletterDialog({ open, onClose, onDismissForever }: { open: boolean; onClose: () => void; onDismissForever: () => void })`. `onDismissForever` fires on successful subscribe AND on "Don't show again"; `onClose` fires on X/Escape/outside-click (Radix `onOpenChange(false)`).

- [ ] **Step 1: Add the localized strings**

In `frontend/src/lib/i18n/strings.ts`, add these keys to **each** language block. Place them right after `disclaimerAccept` in every block.

For the `ca` block:

```typescript
    newsletterHeading: "Vols estar al dia?",
    newsletterSubtext: "Només novetats — no escriurem més d'un cop al mes.",
    newsletterEmailPlaceholder: "correu@exemple.com",
    newsletterSubscribe: "Subscriu-me",
    newsletterDontShow: "No ho tornis a mostrar",
    newsletterSending: "Enviant…",
    newsletterSuccess: "Ja gairebé — revisa la safata d'entrada per confirmar.",
    newsletterError: "No s'ha pogut subscriure. Torna-ho a provar.",
```

For the `es` block:

```typescript
    newsletterHeading: "¿Quieres estar al día?",
    newsletterSubtext: "Solo novedades — no escribiremos más de una vez al mes.",
    newsletterEmailPlaceholder: "correo@ejemplo.com",
    newsletterSubscribe: "Suscribirme",
    newsletterDontShow: "No volver a mostrar",
    newsletterSending: "Enviando…",
    newsletterSuccess: "Ya casi — revisa tu bandeja de entrada para confirmar.",
    newsletterError: "No se pudo suscribir. Inténtalo de nuevo.",
```

For the `en` block:

```typescript
    newsletterHeading: "Want to stay in the loop?",
    newsletterSubtext: "Only updates — we won't message more than once a month.",
    newsletterEmailPlaceholder: "you@example.com",
    newsletterSubscribe: "Subscribe",
    newsletterDontShow: "Don't show again",
    newsletterSending: "Sending…",
    newsletterSuccess: "Almost there — check your inbox to confirm.",
    newsletterError: "Couldn't subscribe. Try again.",
```

- [ ] **Step 2: Write the failing component tests**

Create `frontend/src/components/NewsletterDialog.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { NewsletterDialog } from "./NewsletterDialog";

vi.mock("@/lib/analytics", () => ({ capture: vi.fn() }));
import { capture } from "@/lib/analytics";

function renderDialog(overrides: Partial<Parameters<typeof NewsletterDialog>[0]> = {}) {
  const props = {
    open: true,
    onClose: vi.fn(),
    onDismissForever: vi.fn(),
    ...overrides,
  };
  render(
    <I18nProvider>
      <NewsletterDialog {...props} />
    </I18nProvider>,
  );
  return props;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("NewsletterDialog", () => {
  it("subscribes, shows the confirm message, dismisses forever, and captures anonymously", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 201 }));
    const props = renderDialog();

    await userEvent.type(screen.getByRole("textbox"), "rigger@example.com");
    await userEvent.click(screen.getByRole("button", { name: /subscribe|subscriu|suscribir/i }));

    await waitFor(() =>
      expect(screen.getByText(/almost there|ja gairebé|ya casi/i)).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith("/subscribe", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ email: "rigger@example.com" }),
    }));
    expect(capture).toHaveBeenCalledWith("newsletter_signup");
    expect(capture).not.toHaveBeenCalledWith("newsletter_signup", expect.anything());
    expect(props.onDismissForever).toHaveBeenCalledTimes(1);
    fetchMock.mockRestore();
  });

  it("shows an error and keeps the form when the server fails", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 502 }));
    const props = renderDialog();

    await userEvent.type(screen.getByRole("textbox"), "a@b.com");
    await userEvent.click(screen.getByRole("button", { name: /subscribe|subscriu|suscribir/i }));

    await waitFor(() =>
      expect(screen.getByText(/couldn't subscribe|no s'ha pogut|no se pudo/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(props.onDismissForever).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });

  it("dismisses forever without subscribing on Don't show again", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const props = renderDialog();

    await userEvent.click(
      screen.getByRole("button", { name: /don't show|no ho tornis|no volver/i }),
    );

    expect(props.onDismissForever).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npm test -- NewsletterDialog`
Expected: FAIL (cannot resolve `./NewsletterDialog`)

- [ ] **Step 4: Implement the component**

Create `frontend/src/components/NewsletterDialog.tsx`:

```typescript
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { capture } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";

interface NewsletterDialogProps {
  open: boolean;
  onClose: () => void;
  onDismissForever: () => void;
}

export function NewsletterDialog({ open, onClose, onDismissForever }: NewsletterDialogProps) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(false);
    try {
      const response = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) throw new Error();
      capture("newsletter_signup");
      setDone(true);
      onDismissForever();
    } catch {
      setError(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-w-md">
        <DialogHeader>
          <DialogTitle>{t("newsletterHeading")}</DialogTitle>
        </DialogHeader>
        {done ? (
          <div className="space-y-4 text-sm">
            <p>{t("newsletterSuccess")}</p>
            <Button onClick={onClose}>{t("close")}</Button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={submit}>
            <p className="text-sm text-muted-foreground">{t("newsletterSubtext")}</p>
            <input
              type="email"
              required
              value={email}
              placeholder={t("newsletterEmailPlaceholder")}
              onChange={(event) => setEmail(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2"
            />
            {error ? <p className="text-sm text-destructive">{t("newsletterError")}</p> : null}
            <div className="flex items-center justify-between gap-3">
              <Button type="submit" disabled={sending || !email.trim()}>
                {sending ? t("newsletterSending") : t("newsletterSubscribe")}
              </Button>
              <button
                type="button"
                onClick={onDismissForever}
                className="text-sm text-muted-foreground underline underline-offset-2"
              >
                {t("newsletterDontShow")}
              </button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- NewsletterDialog`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/components/NewsletterDialog.tsx frontend/src/components/NewsletterDialog.test.tsx
git commit -m "feat(frontend): add newsletter signup dialog"
```

---

### Task 4: Wire the dialog into App with localStorage gating

**Files:**
- Modify: `frontend/src/App.tsx` (import, helper, state, welcome `onAccept`, render)
- Test: `frontend/src/App.test.tsx` (add newsletter gating cases)

**Interfaces:**
- Consumes: `NewsletterDialog` from Task 3; `SafetyDisclaimerDialog` (existing, `onAccept` prop at `frontend/src/App.tsx:253-259`).
- Produces: no new exports; behavioral — newsletter opens after welcome accept unless `localStorage["newsletterPrompted"]` is set.

- [ ] **Step 1: Inspect the current welcome wiring**

Read `frontend/src/App.tsx` around the disclaimer state (`const [disclaimerOpen, setDisclaimerOpen] = useState(true);` near line 59) and the render (`<SafetyDisclaimerDialog ... onAccept={() => setDisclaimerOpen(false)} ... />` at lines 253-259) to confirm exact surrounding code before editing.

- [ ] **Step 2: Write the failing App tests**

Add to `frontend/src/App.test.tsx` (mock fetch/analytics as the existing suite does; if the suite has no analytics mock yet, add `vi.mock("@/lib/analytics", () => ({ capture: vi.fn(), initAnalytics: vi.fn(), captureMapSettled: vi.fn() }));` near the top — verify the exact export set imported by `App.tsx` and match it). Add:

```typescript
describe("newsletter prompt", () => {
  it("opens after accepting the welcome dialog when not previously prompted", async () => {
    window.localStorage.removeItem("newsletterPrompted");
    // render <App/> as the existing tests do
    await userEvent.click(screen.getByRole("button", { name: /i understand|ho entenc|lo entiendo/i }));
    expect(await screen.findByText(/want to stay in the loop|vols estar al dia|quieres estar al día/i)).toBeInTheDocument();
  });

  it("does not open the newsletter when already prompted", async () => {
    window.localStorage.setItem("newsletterPrompted", "1");
    // render <App/> as the existing tests do
    await userEvent.click(screen.getByRole("button", { name: /i understand|ho entenc|lo entiendo/i }));
    expect(screen.queryByText(/want to stay in the loop|vols estar al dia|quieres estar al día/i)).not.toBeInTheDocument();
  });
});
```

Note: match the existing `App.test.tsx` render/setup helpers (provider wrapper, fetch stubs) rather than re-inventing them — read the top of the file first and reuse its harness.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npm test -- App`
Expected: FAIL (newsletter text never appears / appears when it should not)

- [ ] **Step 4: Add the localStorage helpers and state**

In `frontend/src/App.tsx`, add the import alongside the other component imports:

```typescript
import { NewsletterDialog } from "./components/NewsletterDialog";
```

Add these module-level helpers near `pickInitialRestrictionAreaMode` (after that function, before `export function App`):

```typescript
const NEWSLETTER_FLAG = "newsletterPrompted";

function newsletterAlreadyPrompted(): boolean {
  try {
    return window.localStorage.getItem(NEWSLETTER_FLAG) === "1";
  } catch {
    return false;
  }
}

function markNewsletterPrompted(): void {
  try {
    window.localStorage.setItem(NEWSLETTER_FLAG, "1");
  } catch {
    // Storage can be unavailable in private mode.
  }
}
```

Add state next to `disclaimerOpen` (near `frontend/src/App.tsx:59`):

```typescript
  const [newsletterOpen, setNewsletterOpen] = useState(false);
```

- [ ] **Step 5: Open the newsletter on welcome accept, and render it**

Change the welcome dialog's `onAccept` (currently `onAccept={() => setDisclaimerOpen(false)}` at `frontend/src/App.tsx:255`) to:

```typescript
        onAccept={() => {
          setDisclaimerOpen(false);
          if (!newsletterAlreadyPrompted()) setNewsletterOpen(true);
        }}
```

Add the dialog render right after the closing `</SafetyDisclaimerDialog ... />` tag, before the closing `</>` (around `frontend/src/App.tsx:259`):

```typescript
      <NewsletterDialog
        open={newsletterOpen}
        onClose={() => setNewsletterOpen(false)}
        onDismissForever={() => {
          markNewsletterPrompted();
          setNewsletterOpen(false);
        }}
      />
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npm test -- App`
Expected: PASS

- [ ] **Step 7: Run the full frontend suite + type/lint gates**

Run: `cd frontend && npm test && npm run build`
Expected: PASS (build typechecks the TS; `StringKey` union compiles only if all three language blocks got the new keys)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): show newsletter prompt after welcome dialog"
```

---

## Operator setup (not code — do before this ships)

- Create a MailerLite account, generate an API key, optionally create a group for this list, and **enable double opt-in** in the account settings.
- Set `HIGHLINER_MAILERLITE_API_KEY` (and optionally `HIGHLINER_MAILERLITE_GROUP_ID`) in the deploy environment.
- Compose/schedule the monthly emails in the MailerLite dashboard.
