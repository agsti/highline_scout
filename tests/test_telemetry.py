import time
from typing import Any

import posthog
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from highliner.core.config import Settings
from highliner.core.telemetry import (
    SERVER_DISTINCT_ID,
    SlowRequestMiddleware,
    api_paths,
    capture_server_event,
    init_posthog,
    init_sentry,
)


class FakeCapture:
    """Stand-in for capture_server_event that records instead of sending."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event: str, properties: dict[str, Any]) -> None:
        self.calls.append((event, properties))


def _app(capture: FakeCapture, threshold_ms: float) -> FastAPI:
    app = FastAPI()

    @app.get("/zones")
    def zones() -> dict[str, str]:
        return {"ok": "fast"}

    @app.get("/slow")
    def slow() -> dict[str, str]:
        time.sleep(0.05)
        return {"ok": "slow"}

    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=threshold_ms,
        environment="test",
        known_paths=api_paths(app),
        capture=capture,
    )
    return app


def test_fast_request_emits_nothing() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=1000.0))

    assert client.get("/zones").status_code == 200

    assert capture.calls == []


def test_slow_request_emits_one_event() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=10.0))

    assert client.get("/slow").status_code == 200

    assert len(capture.calls) == 1
    event, props = capture.calls[0]
    assert event == "slow_request"
    assert props["route"] == "/slow"
    assert props["method"] == "GET"
    assert props["status_code"] == 200
    assert props["duration_ms"] >= 50.0
    assert props["environment"] == "test"
    # Keeps these system events out of person counts.
    assert props["$process_person_profile"] is False


def test_unknown_paths_collapse_to_other() -> None:
    """A hashed static asset must not become its own property value."""
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=0.0))

    client.get("/zones")

    assert capture.calls[0][1]["route"] == "/zones"

    capture.calls.clear()
    # 404s go through the middleware too, and their paths are unbounded.
    client.get("/assets/index-a1b2c3d4.js")

    assert capture.calls[0][1]["route"] == "other"


def test_query_string_never_reaches_properties() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=0.0))

    client.get("/zones?bbox=1,2,3,4&max_len=150")

    _, props = capture.calls[0]
    assert props["route"] == "/zones"
    assert "bbox" not in str(props)


def test_api_paths_lists_only_registered_routes() -> None:
    app = _app(FakeCapture(), threshold_ms=1000.0)

    assert api_paths(app) == frozenset({"/zones", "/slow"})


def test_inits_are_noops_without_credentials() -> None:
    assert init_posthog(Settings(posthog_key=None)) is False
    assert init_sentry(Settings(sentry_dsn=None)) is False


def test_init_posthog_sets_the_key_the_sdk_reads() -> None:
    """The armed key must land on `posthog.api_key`.

    posthog.setup() — which capture() calls internally — builds the default
    client from `posthog.api_key`. The module also carries a vestigial
    `project_api_key` global that nothing reads; assigning to that one leaves
    the client with an empty key, which it logs and then disables itself.
    """
    try:
        assert init_posthog(Settings(posthog_key="phc_test")) is True

        assert posthog.api_key == "phc_test"
        assert posthog.host == "https://eu.i.posthog.com"
    finally:
        posthog.api_key = None
        init_posthog(Settings(posthog_key=None))


def test_capture_server_event_is_silent_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured server must never call into an unarmed PostHog client."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(posthog, "capture",
                        lambda **kwargs: calls.append(kwargs))

    init_posthog(Settings(posthog_key=None))
    capture_server_event("slow_request", {"route": "/zones"})

    assert calls == []


def test_capture_server_event_sends_when_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(posthog, "capture",
                        lambda **kwargs: calls.append(kwargs))

    try:
        assert init_posthog(Settings(posthog_key="phc_test")) is True
        capture_server_event("slow_request", {"route": "/zones"})
    finally:
        # Module-level flag: leave it off so later tests stay silent.
        init_posthog(Settings(posthog_key=None))

    assert len(calls) == 1
    assert calls[0]["distinct_id"] == SERVER_DISTINCT_ID
    assert calls[0]["event"] == "slow_request"
    assert calls[0]["properties"] == {"route": "/zones"}
