"""Scheduler status + manual trigger — workspace 'Run now' buttons."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import scheduler as sched

router = APIRouter()


@router.get("/jobs")
async def jobs() -> dict:
    return {"jobs": sched.list_jobs()}


@router.post("/run/{job_id}")
async def run_now(job_id: str) -> dict:
    ok = sched.run_job_now(job_id)
    if not ok:
        raise HTTPException(404, f"job '{job_id}' not found or scheduler off")
    return {"ok": True, "job": job_id}
