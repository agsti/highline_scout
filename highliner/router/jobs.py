from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from highliner.repositories.jobs import JobStore
from highliner.router.deps import get_jobstore

router = APIRouter()


@router.get("/jobs")
def jobs(store: JobStore = Depends(get_jobstore)) -> dict[str, Any]:
    return {"jobs": store.list()}


@router.get("/jobs/{job_id}")
def job(job_id: str, store: JobStore = Depends(get_jobstore)) -> dict[str, Any]:
    j = store.get(job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    return j
