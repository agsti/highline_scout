# Feedback Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localized feedback form that sends messages to the maintainer through Resend.

**Architecture:** FastAPI validates and rate-limits submissions before a focused service posts a formatted email to Resend. React owns the dialog state, calls a typed API helper, retains failed drafts, and captures only the selected topic after delivery succeeds.

**Tech Stack:** FastAPI, Pydantic, requests, Resend HTTP API, React, TypeScript, Vitest, React Testing Library.

## Global Constraints

- Keep the existing cookieless PostHog settings and all `disable_*` flags unchanged.
- Never send feedback body or reply email to PostHog; capture only `feedback_submitted` with `{ topic }` after HTTP 201.
- Read `HIGHLINER_RESEND_API_KEY`, `HIGHLINER_FEEDBACK_TO`, and `HIGHLINER_FEEDBACK_FROM` only on the server.
- Do not persist submissions after attempting delivery.
- Add each user-visible string to Catalan, Spanish, and English catalogs.

---

### Task 1: Server delivery service

**Files:**
- Create: `highliner/server/services/feedback.py`
- Modify: `highliner/core/config.py`
- Test: `tests/test_feedback.py`

**Interfaces:** `send_feedback(settings: Settings, submission: FeedbackSubmission) -> None`, plus `FeedbackUnavailable` and `FeedbackDeliveryError` exceptions.

- [ ] **Step 1: Write failing delivery tests**

```python
def test_send_feedback_posts_resend_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("highliner.server.services.feedback.requests.post",
                        lambda url, **kwargs: seen.update(url=url, **kwargs) or Response())
    send_feedback(_settings(), _submission("bug", "Broken map", "me@example.com"))
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"] == {"Authorization": "Bearer re_test"}
    assert seen["json"]["subject"] == "[Highline Scout] Bug report"
    assert seen["json"]["reply_to"] == "me@example.com"

def test_send_feedback_requires_all_delivery_settings() -> None:
    with pytest.raises(FeedbackUnavailable):
        send_feedback(_settings(resend_api_key=None), _submission("idea", "Add stars", None))
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_feedback.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement the minimal service**

Add `resend_api_key`, `feedback_to`, and `feedback_from`, all `str | None = None`, to `Settings`. Create the service with this core implementation:

```python
def send_feedback(settings: config.Settings, submission: FeedbackSubmission) -> None:
    if not all((settings.resend_api_key, settings.feedback_to, settings.feedback_from)):
        raise FeedbackUnavailable
    payload = {"from": settings.feedback_from, "to": [settings.feedback_to],
               "subject": f"[Highline Scout] {_SUBJECTS[submission.topic]}",
               "text": _message_text(submission)}
    if submission.reply_email:
        payload["reply_to"] = submission.reply_email
    try:
        requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                      json=payload, timeout=10).raise_for_status()
    except requests.RequestException as error:
        raise FeedbackDeliveryError from error
```

Use fixed subjects `bug: Bug report`, `data: Data issue`, `idea: Idea`, and `other: Feedback`. The plain-text body includes topic, reply address (or `Not supplied`), and message.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_feedback.py -q`

Expected: PASS.

Commit: `git add highliner/core/config.py highliner/server/services/feedback.py tests/test_feedback.py && git commit -m "feat: add Resend feedback delivery"`

### Task 2: Public feedback endpoint

**Files:**
- Create: `highliner/server/router/feedback.py`
- Modify: `highliner/server/app.py`
- Modify: `highliner/server/router/__init__.py`
- Modify: `tests/test_feedback.py`

**Interfaces:** `POST /feedback` accepts `{topic, message, reply_email?}` and returns `201 {"status": "sent"}`. It defines `FeedbackSubmission` consumed by Task 1.

- [ ] **Step 1: Add failing endpoint tests**

```python
def test_feedback_endpoint_sends_valid_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[FeedbackSubmission] = []
    monkeypatch.setattr("highliner.server.router.feedback.send_feedback",
                        lambda settings, submission: sent.append(submission))
    response = TestClient(create_app()).post("/feedback", json={
        "topic": "data", "message": "Duplicate ridge", "reply_email": "me@example.com"})
    assert response.status_code == 201
    assert response.json() == {"status": "sent"}
    assert sent[0].topic == "data"

def test_feedback_endpoint_rejects_blank_messages() -> None:
    response = TestClient(create_app()).post("/feedback", json={"topic": "idea", "message": "  "})
    assert response.status_code == 422

def test_feedback_endpoint_hides_delivery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.server.router.feedback.send_feedback", _raise_delivery_error)
    response = TestClient(create_app()).post("/feedback", json={"topic": "other", "message": "Hello"})
    assert response.status_code == 502
    assert response.json()["detail"] == "feedback could not be sent; try again"
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_feedback.py -q`

Expected: FAIL with 404 because `/feedback` is not registered.

- [ ] **Step 3: Implement validation, errors, and rate limit**

```python
class FeedbackSubmission(BaseModel):
    topic: Literal["bug", "data", "idea", "other"]
    message: str
    reply_email: EmailStr | None = None

    @field_validator("message")
    @classmethod
    def message_is_valid(cls, value: str) -> str:
        if not value.strip() or len(value) > 4000:
            raise ValueError("message must contain 1 to 4000 characters")
        return value

@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(request: Request, submission: FeedbackSubmission) -> dict[str, str]:
    _enforce_rate_limit(request.client.host if request.client else "unknown")
    try:
        send_feedback(config.settings, submission)
    except FeedbackUnavailable as error:
        raise HTTPException(503, "feedback is not configured") from error
    except FeedbackDeliveryError as error:
        raise HTTPException(502, "feedback could not be sent; try again") from error
    return {"status": "sent"}
```

Use a module-level `dict[str, list[float]]`, prune values older than 3600 seconds, and reject the sixth request by one IP with `429 "too many feedback submissions; try later"`. Register the router in `app.py`.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_feedback.py -q && uv run ruff check highliner tests && uv run mypy highliner tests`

Expected: PASS, including missing configuration and sixth-request 429 tests.

Commit: `git add highliner/server/router/feedback.py highliner/server/app.py highliner/server/router/__init__.py tests/test_feedback.py && git commit -m "feat: accept feedback submissions"`

### Task 3: Feedback client and dialog

**Files:**
- Create: `frontend/src/components/FeedbackDialog.tsx`
- Create: `frontend/src/components/FeedbackDialog.test.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/api.test.ts`
- Modify: `frontend/src/lib/i18n/strings.ts`
- Modify: `frontend/src/lib/i18n/i18n.test.tsx`

**Interfaces:** `submitFeedback({ topic, message, replyEmail }): Promise<void>` and `<FeedbackDialog open onOpenChange>`.

- [ ] **Step 1: Write failing dialog tests**

```tsx
it("submits the topic and shows confirmation", async () => {
  const user = userEvent.setup();
  submitFeedbackMock.mockResolvedValue(undefined);
  renderDialog();
  await user.selectOptions(screen.getByLabelText("Topic"), "data");
  await user.type(screen.getByLabelText("Message"), "Duplicate ridge");
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  await waitFor(() => expect(submitFeedbackMock).toHaveBeenCalledWith(
    { topic: "data", message: "Duplicate ridge", replyEmail: "" },
  ));
  expect(screen.getByText("Feedback sent")).toBeInTheDocument();
  expect(captureMock).toHaveBeenCalledWith("feedback_submitted", { topic: "data" });
});

it("preserves the draft on delivery failure", async () => {
  const user = userEvent.setup();
  submitFeedbackMock.mockRejectedValue(new ApiError(502, "failed"));
  renderDialog();
  await user.type(screen.getByLabelText("Message"), "Map issue");
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(await screen.findByText("Could not send feedback. Try again.")).toBeInTheDocument();
  expect(screen.getByLabelText("Message")).toHaveValue("Map issue");
  expect(captureMock).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Verify red**

Run: `npm test -- --run frontend/src/components/FeedbackDialog.test.tsx frontend/src/lib/api.test.ts`

Expected: FAIL because the dialog and API client are missing.

- [ ] **Step 3: Implement form behavior and localization**

```ts
export async function submitFeedback(payload: FeedbackPayload): Promise<void> {
  const response = await fetch("/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic: payload.topic, message: payload.message,
      reply_email: payload.replyEmail || undefined }),
  });
  if (!response.ok) throw await parseError(response);
}
```

Use existing dialog primitives with labelled native select, required textarea (`maxLength={4000}`), optional `type="email"` input, pending disabled state, failure draft preservation, and success confirmation. Add to all language catalogs: `feedbackTitle`, `feedbackIntro`, `feedbackTopic`, `feedbackTopicBug`, `feedbackTopicData`, `feedbackTopicIdea`, `feedbackTopicOther`, `feedbackMessage`, `feedbackReplyEmail`, `feedbackReplyHint`, `feedbackSend`, `feedbackSending`, `feedbackSent`, `feedbackSentBody`, `feedbackRetry`, `feedbackSendError`.

- [ ] **Step 4: Verify green and commit**

Run: `npm test -- --run frontend/src/components/FeedbackDialog.test.tsx frontend/src/lib/api.test.ts frontend/src/lib/i18n/i18n.test.tsx`

Expected: PASS.

Commit: `git add frontend/src/components/FeedbackDialog.tsx frontend/src/components/FeedbackDialog.test.tsx frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/lib/i18n/strings.ts frontend/src/lib/i18n/i18n.test.tsx && git commit -m "feat: add feedback form"`

### Task 4: Menu, app integration, and settings sample

**Files:**
- Modify: `frontend/src/components/NavMenu.tsx`
- Modify: `frontend/src/components/NavMenu.test.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `.env.sample`

**Interfaces:** `NavMenuProps` gains `onFeedback: () => void`; `App` owns `feedbackOpen` and renders `FeedbackDialog`.

- [ ] **Step 1: Write a failing menu callback test**

```tsx
it("opens feedback and closes the menu", async () => {
  const user = userEvent.setup();
  const { onFeedback } = renderMenu();
  await openMenu(user);
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(onFeedback).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", { name: "About Highline Scout" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Verify red**

Run: `npm test -- --run frontend/src/components/NavMenu.test.tsx`

Expected: FAIL because `onFeedback` does not exist.

- [ ] **Step 3: Implement wiring and documented configuration**

Remove the `feedbackNoted` placeholder state and `feedbackComingSoon` strings. Call `select(onFeedback)` in `NavMenu`; pass the callback through `MapChrome`; add `const [feedbackOpen, setFeedbackOpen] = useState(false)` to `App`; render `<FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />`. Add only commented Resend environment-variable examples to `.env.sample`.

- [ ] **Step 4: Verify green and commit**

Run: `npm test -- --run frontend/src/components/NavMenu.test.tsx frontend/src/components/FeedbackDialog.test.tsx && npm run build`

Expected: PASS and successful production build.

Commit: `git add frontend/src/components/NavMenu.tsx frontend/src/components/NavMenu.test.tsx frontend/src/components/MapChrome.tsx frontend/src/App.tsx .env.sample && git commit -m "feat: open feedback form from menu"`

### Task 5: Full verification

- [ ] **Step 1: Run all checks**

Run: `just check && just test && just test-web && just build-web`

Expected: all lint, type, dead-code, Python tests, frontend tests, and production build PASS.

- [ ] **Step 2: Inspect final scope**

Run: `git status --short && git diff --check HEAD~4..HEAD`

Expected: only intended feedback changes are staged/committed; preserve unrelated user changes.
