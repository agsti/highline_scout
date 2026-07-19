import pytest
from fastapi.testclient import TestClient

from highliner.server.app import create_app


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    """Clear rate limiter state before each test to ensure isolation."""
    from highliner.server.router import subscribe
    subscribe._ATTEMPTS.clear()


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
