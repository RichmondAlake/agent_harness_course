"""Chapter 8: focus sessions."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import focus, scratchfs, tasks
from backend.routers.deps import ready
from backend.schemas import CaptureReq, FocusStartReq, FocusStopReq

router = APIRouter(prefix="/api/focus_sessions", tags=["focus_sessions"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    current = focus.running()
    return {"chapter": "Focus sessions", **focus.status(), "tasks": tasks.governed()[:12],
            "parked": scratchfs.distractions(current["session_id"]) if current else [],
            "demo": "The demo-seconds control shortens the real timer. The model-facing tool has no "
                    "such control and clamps its minutes to 5 to 90."}


@router.post("/start")
async def start(req: FocusStartReq):
    """Start from the UI. ``demo_seconds`` compresses the timer; the log still records planned minutes."""
    try:
        return focus.start(req.task_id, req.minutes, real_seconds=req.demo_seconds)
    except KeyError as exc:
        raise HTTPException(404, f"No such task: {exc}") from exc


@router.post("/stop")
async def stop(req: FocusStopReq):
    return focus.stop(req.reason)


@router.post("/distraction")
async def distraction(req: CaptureReq):
    return focus.distraction(req.text)
