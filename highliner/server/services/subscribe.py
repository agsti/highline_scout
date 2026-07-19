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
