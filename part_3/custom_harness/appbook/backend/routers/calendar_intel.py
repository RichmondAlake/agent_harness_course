"""Chapter 7: calendar intelligence."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import approval, calendar_intel, clock, tasks, tools, world
from backend.routers.deps import ready
from backend.schemas import BlocksReq

router = APIRouter(prefix="/api/calendar_intel", tags=["calendar_intel"], dependencies=[Depends(ready)])


@router.get("/status")
async def status(date: str | None = None):
    day = clock.parse_day(date)
    shown = await calendar_intel.overview(day)
    return {"chapter": "Calendar intelligence", "clock": clock.status(), "day": shown,
            "week": await calendar_intel.week(day), "layers": calendar_intel.layers(shown["events"]),
            "top_tasks": tasks.governed()[:3]}


@router.post("/plan")
async def plan(req: BlocksReq):
    """Place tasks into free slots. Nothing is written to the calendar."""
    return await calendar_intel.plan(req.task_ids or None, clock.parse_day(req.date))


@router.post("/plan/request_approval")
async def request_approval(req: BlocksReq):
    """Draft one calendar event per block. Each waits for a decision in the approvals chapter."""
    planned = await calendar_intel.plan(req.task_ids or None, clock.parse_day(req.date))
    drafted = []
    for block in planned["blocks"]:
        arguments = tools.validate("calendar_create_event", {
            "title": f"Focus: {block['title']}", "start": block["start"], "end": block["end"],
            "kind": "focus", "attendees": [world.owner_email()],
            "description": f"Time block for {block['task_id']}, part {block['part']}.",
            "reason": f"Protect {block['pomodoros']} Pomodoro(s) for {block['task_id']}."}).model_dump()
        drafted.append(approval.draft(
            "calendar_create_event", arguments, reason=arguments["reason"],
            risk=await approval.assess("calendar_create_event", arguments),
            thread_id="manual", session_id=clock.session_id(), run_id=None, origin="manual"))
    return {**planned, "drafted": drafted}


@router.get("/prep/{event_id}")
async def prep(event_id: str):
    found = await calendar_intel.meeting_prep(event_id)
    if found is None:
        raise HTTPException(404, "No such event in the next two weeks")
    thread = found.get("related_thread")
    if thread and thread["category"] == "quarantine":
        found["related_thread"] = {**thread, "body": ""}
    return found
