"""Chapter 12: timers and scheduled work."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import clock, routines
from backend.core.scheduler import scheduler
from backend.routers.deps import ready
from backend.schemas import RunNowReq, ScheduleReq, SimulateReq, SwitchReq

router = APIRouter(prefix="/api/routines", tags=["routines"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    return {"chapter": "Timers and scheduled work", **routines.status(), "scheduler": scheduler.status(),
            "jobs": scheduler.jobs(80), "clock": clock.status(),
            "states": {"ARMED": "waiting for its time", "FIRED": "claimed and running",
                       "DELIVERED": "finished and its notification was delivered",
                       "CANCELLED": "stopped before it fired", "FAILED": "its handler raised an error"}}


@router.get("/jobs")
async def jobs(limit: int = 80):
    return {"jobs": scheduler.jobs(limit), "clock": clock.status()}


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    from backend.core import focus

    job = scheduler.job(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    if job["state"] != "ARMED":
        raise HTTPException(409, f"This job is already {job['state']}")
    running = focus.running()
    if job["kind"] == "pomodoro" and running and running["job_id"] == job_id:
        return {"job": scheduler.job(job_id), "focus": focus.stop("Timer cancelled from the appbook.")}
    return {"job": scheduler.cancel(job_id)}


@router.post("/jobs/{job_id}/fire")
async def fire(job_id: str):
    """Fire an armed job now instead of waiting for its time."""
    try:
        return {"job": await scheduler.run_inline(job_id)}
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/run/{kind}")
async def run_now(kind: str, req: RunNowReq | None = None):
    payload = {key: value for key, value in (req.model_dump() if req else {}).items() if value}
    if kind == "meeting_prep" and "event_id" not in payload:
        raise HTTPException(400, "meeting_prep needs an event_id")
    if kind == "vip_alert" and "thread_id" not in payload:
        raise HTTPException(400, "vip_alert needs a thread_id")
    try:
        return {"job": await routines.run_now(kind, payload)}
    except KeyError as exc:
        raise HTTPException(404, f"No such routine: {exc}") from exc


@router.post("/triggers/evaluate")
async def evaluate():
    return await routines.evaluate_triggers()


@router.post("/schedules/{name}")
async def schedule(name: str, req: ScheduleReq):
    try:
        return scheduler.set_schedule(name, enabled=req.enabled, local_time=req.local_time)
    except KeyError as exc:
        raise HTTPException(404, "No such schedule") from exc


@router.post("/automation")
async def automation(req: SwitchReq):
    return {"automation_enabled": scheduler.set_automation(req.enabled)}


@router.post("/simulate_week")
async def simulate(req: SimulateReq):
    try:
        return await routines.simulate_week(req.days)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
