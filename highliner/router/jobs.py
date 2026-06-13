from fastapi import APIRouter, Depends, HTTPException

from highliner.router.deps import get_jobstore

router = APIRouter()


@router.get("/jobs")
def jobs(store=Depends(get_jobstore)):
    return {"jobs": store.list()}


@router.get("/jobs/{job_id}")
def job(job_id: str, store=Depends(get_jobstore)):
    j = store.get(job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    return j
