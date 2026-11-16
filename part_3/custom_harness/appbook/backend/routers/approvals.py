"""Chapter 10: approval gates and the action log."""
from fastapi import APIRouter, Depends, HTTPException

import policy
from pydantic import ValidationError

from backend.core import approval, clock, inbox, scratchfs, store, tasks, tools, world
from backend.core.agent import ThreadBusy, agent
from backend.core.memory import memory_provider
from backend.core.workspace import workspace
from backend.routers.deps import ready
from backend.schemas import DecisionReq, DraftReq, RiskReq, WrapReq

router = APIRouter(prefix="/api/approvals", tags=["approvals"], dependencies=[Depends(ready)])


def _context() -> tools.ToolContext:
    return tools.ToolContext(thread_id="manual", session_id=clock.session_id(), origin="manual")


@router.get("/status")
async def status():
    return {"chapter": "Approval gates and action log", "tiers": approval.TIERS,
            "pending": approval.pending(), "log": approval.log(60),
            "safe_mode": await workspace.safe_mode(), "practice": workspace.practising(),
            "tripwire": approval.TRIPWIRE_FINDING,
            "gated_tools": [item for item in tools.catalogue() if item["tier"] in {"approval", "conditional"}],
            "states": "DRAFTED, then APPROVED and EXECUTED, or REJECTED. FAILED when the workspace refuses.",
            "delivery": "Recorded separately from approval: an approved action may be held by safe mode."}


@router.post("/draft")
async def draft(req: DraftReq):
    """Draft a gated action by hand. Nothing happens until it is approved."""
    try:
        args = tools.validate(req.name, {**req.arguments, "reason": req.reason})
    except ValidationError as exc:
        raise HTTPException(400, exc.errors(include_url=False, include_input=False)) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(403, str(exc).strip("'\"")) from exc
    if await tools.tier_for(req.name, args) != "approval":
        raise HTTPException(400, f"{req.name} is automatic here: nobody else would see the result.")
    refused = await tools.refusal(req.name, args)
    if refused:
        raise HTTPException(409, refused["detail"])
    arguments = args.model_dump()
    return approval.draft(req.name, arguments, reason=req.reason,
                          risk=await approval.assess(req.name, arguments),
                          thread_id="manual", session_id=clock.session_id(), run_id=None, origin="manual")


@router.post("/{action_id}/decide")
async def decide(action_id: str, req: DecisionReq):
    """Approve or reject one action. A decision on an agent's action resumes its run."""
    action = approval.get(action_id)
    if action is None:
        raise HTTPException(404, "No such action")
    if action["state"] != "DRAFTED":
        raise HTTPException(409, f"This action is already {action['state']}")
    if action["origin"] != "manual":
        try:
            run = await agent.resume(action["thread_id"], {action_id: req.decision}, req.note)
        except ThreadBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"action": approval.get(action_id), "run": run}
    approval.decide(action_id, req.decision, req.note)
    if req.decision == "approve":
        result = await tools.execute(action["tool_name"],
                                     tools.validate(action["tool_name"], action["payload"]), _context())
        approval.executed(action_id, action["tool_name"], action["payload"], result)
    return {"action": approval.get(action_id), "run": None}


@router.post("/{action_id}/undo")
async def undo(action_id: str):
    """Reverse an automatic action that only touched harness state."""
    action = approval.get(action_id)
    if action is None:
        raise HTTPException(404, "No such action")
    if not action["undoable"]:
        raise HTTPException(409, action["undo_hint"] or "This action cannot be undone from here.")
    result, tool = action["result"] or {}, action["tool_name"]
    if tool == "task_add":
        if result.get("status") != "created":
            raise HTTPException(409, "No task was created, so there is nothing to undo.")
        outcome = {"task": tasks.set_status(result["task_id"], "DROPPED")["task_id"], "status": "DROPPED"}
    elif tool == "task_complete":
        outcome = {"task": tasks.set_status(result["task_id"], "OPEN")["task_id"], "status": "OPEN"}
    elif tool == "memory_write":
        outcome = {"memory_id": result["memory_id"], "deleted": memory_provider.delete(result["memory_id"])}
    else:
        outcome = {"path": result["path"],
                   "deleted": scratchfs.ScratchFS(result["session_id"]).delete(result["path"])}
    return approval.mark_undone(action_id, outcome)


@router.post("/risk")
async def risk(req: RiskReq):
    """Recipient risk for a message, before anything is drafted."""
    participants: list[str] = []
    if req.thread_id:
        found = await inbox.thread(req.thread_id)
        if found is None:
            raise HTTPException(404, "No such thread")
        participants = found["participants"]
    return {**policy.recipient_risk([*req.to, *req.cc], participants, store.contacts(), world.own_domain()),
            "thread_participants": participants,
            "rule": "High when a recipient is neither on the thread nor a known contact."}


@router.post("/wrap")
async def wrap(req: WrapReq):
    """What the model is shown for a piece of external text, and what the tripwire sees in it."""
    return {"wrapped": policy.wrap_untrusted(req.source, req.ref, req.text),
            "patterns": policy.detect_injection(req.text),
            "pattern_names": [name for name, _ in policy.INJECTION_PATTERNS],
            "tripwire": approval.TRIPWIRE_FINDING}
