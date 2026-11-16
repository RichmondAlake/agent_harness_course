"""The header, the clock, the event stream and notifications."""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.core import clock, notifications, runtime
from backend.core.events import bus
from backend.routers.deps import ready
from backend.schemas import ClockReq, ResetReq

router = APIRouter(prefix="/api", tags=["harness"])


@router.get("/status")
async def status():
    """Answers while the harness is still warming, so the page can say so."""
    return runtime.status()


@router.get("/health")
async def health():
    """Whether the server answers and whether the harness has finished starting. No secrets."""
    state = runtime.status()
    return {"status": "ok", "ready": bool(state.get("ready")), "error": state.get("error"),
            "responder": (state.get("responder") or {}).get("label"), "substrate": state.get("substrate")}


@router.get("/clock", dependencies=[Depends(ready)])
async def read_clock():
    """The clock, with moments worth jumping to: each routine's next time and the next meeting."""
    from datetime import timedelta

    from backend.core import calendar_intel
    from backend.core.scheduler import first_occurrence, scheduler
    from backend.core.workspace import WorkspaceError

    now = clock.now()
    start = clock.at(now.date(), "00:00") - timedelta(minutes=1)
    presets = [{"label": f"{item['label']}, {moment.strftime('%A %H:%M')}",
                "now": moment.isoformat(timespec="minutes")}
               for item in scheduler.schedules()
               for moment in [first_occurrence(item["days"], item["local_time"], start)]]
    try:
        ahead = [item for item in await calendar_intel.events_between(now.date(), now.date() + timedelta(days=7))
                 if item["kind"] == "meeting" and clock.localise(item["start"]) > now]
        if ahead:
            before = clock.localise(ahead[0]["start"]) - timedelta(minutes=20)
            presets.append({"label": f"20 minutes before the next meeting, {before.strftime('%A %H:%M')}",
                            "now": before.isoformat(timespec="minutes")})
    except WorkspaceError:
        pass
    presets.append({"label": "31 days on, to see what goes stale",
                    "now": (now + timedelta(days=31)).isoformat(timespec="minutes")})
    return {**clock.status(), "presets": presets}


@router.post("/clock", dependencies=[Depends(ready)])
async def set_clock(req: ClockReq):
    """Move the clock to a moment. Without one, return to the workspace's own clock."""
    if req.now:
        try:
            clock.localise(req.now)
        except ValueError as exc:
            raise HTTPException(400, f"That moment could not be read: {exc}") from exc
    return await runtime.set_clock(req.now)


@router.post("/clock/reset", dependencies=[Depends(ready)])
async def reset_clock():
    return await runtime.set_clock(None)


@router.post("/reset", dependencies=[Depends(ready)])
async def reset(req: ResetReq):
    return await runtime.reset()


@router.get("/notifications", dependencies=[Depends(ready)])
async def list_notifications(limit: int = 30):
    return {"unread": notifications.unread(), "notifications": notifications.recent(limit)}


@router.post("/notifications/{notification_id}/read", dependencies=[Depends(ready)])
async def read_notification(notification_id: str):
    return {"notification_id": notification_id, "changed": notifications.mark_read(notification_id),
            "unread": notifications.unread()}


@router.get("/events")
async def events(request: Request):
    """One stream for run progress, timers, notifications, actions and table activity."""
    async def generate():
        queue = bus.subscribe()
        try:
            yield {"event": "ready", "data": json.dumps({"status": "connected"})}
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": event["topic"], "data": json.dumps(event, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"status": "alive"})}
        finally:
            bus.unsubscribe(queue)
    return EventSourceResponse(generate())
