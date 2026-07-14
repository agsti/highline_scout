"""Product analytics (PostHog) and error reporting (GlitchTip via Sentry).

Deliberately thin. The backend only ever sees viewport reads — a slider drag or
a map pan fires many /zones requests — so per-request events would record
traffic, not intent. User intent is captured in the browser instead. Here we
emit exactly one thing the browser cannot see: a request that was too slow.

Errors are *not* sent to PostHog; they go to GlitchTip through sentry_sdk, so
nothing is counted twice.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import posthog
import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from highliner.core.config import Settings

# Backend events are anonymous system events: no client distinct_id is forwarded
# and no person profile is created (see $process_person_profile below), so they
# never pollute the frontend's unique-visitor counts.
SERVER_DISTINCT_ID = "server"

_posthog_enabled = False


def init_sentry(settings: Settings) -> bool:
    """Send unhandled exceptions to GlitchTip. No DSN configured means no-op."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # /zones fires on every map pan; tracing it would flood the self-hosted
        # GlitchTip with transactions that add nothing over `slow_request`.
        # Percentage of requests recorded for performance monitoring
        traces_sample_rate=0.3,
        # GlitchTip does not support Sentry session tracking
        auto_session_tracking=False,
    )
    return True


def init_posthog(settings: Settings) -> bool:
    """Arm the PostHog client. No key configured means no-op."""
    global _posthog_enabled
    if not settings.posthog_key:
        _posthog_enabled = False
        return False
    # `api_key`, not `project_api_key`: the latter is a vestigial module global
    # the v7 SDK never reads, so the default client would be built keyless.
    posthog.api_key = settings.posthog_key
    posthog.host = settings.posthog_host
    _posthog_enabled = True
    return True


def capture_server_event(event: str, properties: dict[str, Any]) -> None:
    """Send an anonymous system event. No-op unless PostHog was armed.

    Mirrors the frontend's capture(): callers never have to check whether
    telemetry is configured, and an unconfigured server never touches the
    network.
    """
    if not _posthog_enabled:
        return
    posthog.capture(
        distinct_id=SERVER_DISTINCT_ID,
        event=event,
        properties=properties,
    )


def shutdown_telemetry() -> None:
    """Flush the PostHog queue; its sender is a background thread."""
    if not _posthog_enabled:
        return
    posthog.shutdown()


def api_paths(app: FastAPI) -> frozenset[str]:
    """The paths FastAPI actually registered.

    Anything else — notably every hashed asset under the StaticFiles mount, and
    every 404 — collapses to "other" so unbounded paths can't explode event
    property cardinality.
    """
    return frozenset(
        route.path for route in app.routes if isinstance(route, APIRoute)
    )


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """Emit one `slow_request` event per request that exceeds the threshold.

    Emits nothing for a normal request. That is the point: the alternative — an
    event per request — would bill for recording the same map pan forty times.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        threshold_ms: float,
        environment: str,
        known_paths: frozenset[str],
        capture: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(app)
        self.threshold_ms = threshold_ms
        self.environment = environment
        self.known_paths = known_paths
        self._capture = capture or capture_server_event

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0

        if duration_ms >= self.threshold_ms:
            path = request.url.path
            properties: dict[str, Any] = {
                # Path only — never request.url, which carries the bbox.
                "route": path if path in self.known_paths else "other",
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "environment": self.environment,
                "$process_person_profile": False,
            }
            self._capture("slow_request", properties)
        return response
