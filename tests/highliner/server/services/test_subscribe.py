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
