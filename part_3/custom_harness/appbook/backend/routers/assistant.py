"""The assistant workspace: chat, agenda, tasks, triage, capture and the day plan.

This is the product view of the running system. The chapters that follow are
the teaching view of the same state, not separate demonstrations.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from backend.core import approval, calendar_intel, clock, focus, notifications, scratchfs, tasks
from backend.core.agent import ThreadBusy, agent
from backend.core.scheduler import scheduler
from backend.core.workspace import WorkspaceError
from backend.routers.deps import ready
from backend.schemas import ResumeReq, SnoozeReq, TaskPatchReq, TaskReq, TurnReq

router = APIRouter(prefix="/api/assistant", tags=["assistant"], dependencies=[Depends(ready)])
STARTERS = ["Prepare my morning brief.", "Triage my inbox and turn anything actionable into tasks.",
            "Time-block my top three tasks for today.", "Prepare me for my next meeting.",
            "What should I know before I plan Friday?", "Wrap up my day."]


def _tasks() -> dict:
    health = tasks.health()
    return {"open": tasks.governed(), "snoozed": [item for item in tasks.governed(include_snoozed=True)
                                                  if item["snoozed"]],
            "done": tasks.recently_done(),
            "slipping": [item["task_id"] for item in health["slipping"]],
            "stale": [item["task_id"] for item in health["stale"]],
            "order": "urgent first, then priority, then due date"}


@router.get("/status")
async def status():
    """Everything the workspace shows beside the chat, in one read."""
    try:
        agenda = await calendar_intel.overview(clock.today())
    except WorkspaceError as exc:
        agenda = {"error": str(exc), "events": [], "free_slots": [], "meeting_rule_violations": []}
    session = scratchfs.session()
    return {"clock": clock.status(), "agenda": agenda, "tasks": _tasks(),
            "plan": session["plan"], "inbox": session["inbox"], "session": {
                "session_id": session["session_id"], "status": session["status"]},
            "focus": focus.running(), "pending_actions": approval.pending(),
            "timers": [item for item in scheduler.jobs(40) if item["state"] == "ARMED"],
            "notifications": notifications.recent(8), "unread": notifications.unread(),
            "starters": STARTERS}


@router.post("/turn")
async def turn(req: TurnReq):
    """One typed request through the loop. Returns when it completes or pauses for approval."""
    try:
        return await agent.run(req.message, thread_id=req.thread_id, session_id=req.session_id,
                               responder=req.responder, run_id=req.run_id)
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/resume")
async def resume(req: ResumeReq):
    """Decide the drafted actions of a paused run and continue that same run."""
    try:
        return await agent.resume(req.thread_id, req.decisions, req.note)
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(409, str(exc).strip("'\"")) from exc


@router.get("/threads")
async def threads():
    return {"threads": agent.threads()}


@router.get("/thread/{thread_id}")
async def thread(thread_id: str):
    return await agent.transcript(thread_id)


@router.get("/tasks")
async def list_tasks():
    return _tasks()


@router.post("/tasks")
async def add_task(req: TaskReq):
    try:
        return tasks.add(req.title, priority=req.priority, due_at=req.due_at,
                         est_pomodoros=req.est_pomodoros, source_type="chat")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/tasks/{task_id}")
async def patch_task(task_id: str, req: TaskPatchReq):
    try:
        return tasks.update(task_id, **req.model_dump())
    except KeyError as exc:
        raise HTTPException(404, "No such task") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/tasks/{task_id}/{action}")
async def act_on_task(task_id: str, action: str, req: SnoozeReq | None = None):
    """complete, reopen, drop, snooze or wake one task."""
    try:
        if action in {"complete", "reopen", "drop"}:
            return tasks.set_status(task_id, {"complete": "DONE", "reopen": "OPEN", "drop": "DROPPED"}[action])
        if action == "wake":
            return tasks.clear(task_id, "snoozed_until")
        if action == "snooze":
            until = (req.until if req and req.until else
                     (clock.now() + timedelta(hours=(req.hours if req and req.hours else 24))).isoformat())
            return tasks.update(task_id, snoozed_until=until)
    except KeyError as exc:
        raise HTTPException(404, "No such task") from exc
    raise HTTPException(400, "Unknown action. Use complete, reopen, drop, snooze or wake.")
