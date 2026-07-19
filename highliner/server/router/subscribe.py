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
