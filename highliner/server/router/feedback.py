"""Public feedback endpoint."""

from collections import defaultdict
from time import monotonic
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from highliner.core import config
from highliner.server.services.feedback import (
    FeedbackDeliveryError,
    FeedbackSubmission,
    FeedbackUnavailable,
    send_feedback,
)

router = APIRouter()
_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 3600
_MAX_ATTEMPTS = 5


class FeedbackRequest(BaseModel):
    """Validated public payload without retaining it beyond delivery."""

    topic: Literal["bug", "data", "idea", "other"]
    message: str
    reply_email: str | None = None

    @field_validator("message")
    @classmethod
    def message_is_valid(cls, value: str) -> str:
        if not value.strip() or len(value) > 4000:
            raise ValueError("message must contain 1 to 4000 characters")
        return value

    @field_validator("reply_email")
    @classmethod
    def reply_email_is_valid(cls, value: str | None) -> str | None:
        if value is not None and (len(value) > 254 or "@" not in value):
            raise ValueError("reply email must be valid")
        return value


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(request: Request, payload: FeedbackRequest) -> dict[str, str]:
    """Validate, rate limit, and forward one feedback email."""
    _enforce_rate_limit(request.client.host if request.client else "unknown")
    submission = FeedbackSubmission(**payload.model_dump())
    try:
        send_feedback(config.settings, submission)
    except FeedbackUnavailable as error:
        raise HTTPException(503, "feedback is not configured") from error
    except FeedbackDeliveryError as error:
        raise HTTPException(502, "feedback could not be sent; try again") from error
    return {"status": "sent"}


def _enforce_rate_limit(ip: str) -> None:
    now = monotonic()
    attempts = [time for time in _ATTEMPTS[ip] if now - time < _WINDOW_SECONDS]
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(429, "too many feedback submissions; try later")
    attempts.append(now)
    _ATTEMPTS[ip] = attempts
