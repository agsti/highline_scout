"""Liveness probe for the reverse proxy and any external uptime monitor.

Deliberately a bare liveness check: it proves the process accepted the request
and a worker answered — the failure mode a hung worker exhibits. It touches no
data partitions on purpose. A readiness-style check that failed on a transient
data issue would only cause needless restarts / de-registration from the
load balancer, taking a serving process down over a non-fatal condition.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
