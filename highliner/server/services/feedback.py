"""Feedback email delivery through Resend."""

from dataclasses import dataclass
from typing import Literal

import requests

from highliner.core import config

_SUBJECTS = {
    "bug": "Bug report", "data": "Data issue", "idea": "Idea", "other": "Feedback",
}


@dataclass(frozen=True)
class FeedbackSubmission:
    topic: Literal["bug", "data", "idea", "other"]
    message: str
    reply_email: str | None


class FeedbackUnavailable(Exception):
    """Feedback email has not been configured."""


class FeedbackDeliveryError(Exception):
    """Resend did not accept the feedback email."""


def send_feedback(settings: config.Settings, submission: FeedbackSubmission) -> None:
    """Deliver one feedback message without retaining its contents."""
    if not all((settings.resend_api_key, settings.feedback_to, settings.feedback_from)):
        raise FeedbackUnavailable
    payload: dict[str, object] = {
        "from": settings.feedback_from,
        "to": [settings.feedback_to],
        "subject": f"[Highline Scout] {_SUBJECTS[submission.topic]}",
        "text": _message_text(submission),
    }
    if submission.reply_email:
        payload["reply_to"] = submission.reply_email
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise FeedbackDeliveryError from error


def _message_text(submission: FeedbackSubmission) -> str:
    reply = submission.reply_email or "Not supplied"
    return (
        f"Topic: {_SUBJECTS[submission.topic]}\\n"
        f"Reply email: {reply}\\n\\n"
        f"{submission.message}"
    )
