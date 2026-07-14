import pytest
from highliner.core.config import Settings
from highliner.server.services.feedback import FeedbackSubmission, send_feedback


class _Response:
    def raise_for_status(self) -> None:
        pass


def _settings() -> Settings:
    return Settings(
        resend_api_key="re_test",
        feedback_to="owner@example.com",
        feedback_from="Scout <feedback@example.com>",
    )


def test_send_feedback_posts_a_plain_text_resend_email(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> _Response:
        seen["url"] = url
        seen.update(kwargs)
        return _Response()

    monkeypatch.setattr("highliner.server.services.feedback.requests.post", post)

    send_feedback(_settings(), FeedbackSubmission(
        topic="bug",
        message="The zone count is wrong.",
        reply_email="rigger@example.com",
    ))

    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"] == {"Authorization": "Bearer re_test"}
    assert seen["json"] == {
        "from": "Scout <feedback@example.com>",
        "to": ["owner@example.com"],
        "subject": "[Highline Scout] Bug report",
        "text": (
            "Topic: Bug report\n"
            "Reply email: rigger@example.com\n\n"
            "The zone count is wrong."
        ),
        "reply_to": "rigger@example.com",
    }
