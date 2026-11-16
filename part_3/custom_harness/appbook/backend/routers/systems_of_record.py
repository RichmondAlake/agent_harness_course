"""Chapter 3: systems of record and MCP."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import tools
from backend.core.workspace import (ALLOWLIST, READ_TOOLS, TIER_RULES, ToolNotAllowed, WorkspaceError,
                                    last_turn_calls, workspace)
from backend.routers.deps import ready
from backend.schemas import ToolReq

router = APIRouter(prefix="/api/systems_of_record", tags=["systems_of_record"],
                   dependencies=[Depends(ready)])
CONTEXT = tools.ToolContext(thread_id="chapter-systems-of-record", session_id="chapter", origin="manual")


@router.get("/status")
async def status():
    offered = workspace.catalogue()
    every = [item for items in offered.values() for item in items]
    return {"chapter": "Systems of record and MCP", "gateway": workspace.status(),
            "servers": offered, "tier_rules": TIER_RULES,
            "counts": {"offered": len(every), "allowlisted": sum(item["exposed"] for item in every),
                       "never_exposed": sum(not item["exposed"] for item in every)},
            "never_exposed": [item["name"] for item in every if not item["exposed"]],
            "systems_of_record": [
                {"data": "Mail", "home": "mail server (MCP)", "held_by_harness": "No. Read on demand."},
                {"data": "Events", "home": "calendar (MCP)", "held_by_harness": "No. Read on demand."},
                {"data": "Pages", "home": "notes (MCP)", "held_by_harness": "No. Read on demand."},
                {"data": "Tasks", "home": "ppa_tasks", "held_by_harness": "Yes. They have no other home."},
                {"data": "Focus sessions", "home": "ppa_focus_sessions", "held_by_harness": "Yes."},
                {"data": "Contacts and VIPs", "home": "ppa_contacts",
                 "held_by_harness": "Yes, derived by the gateway from sent mail."},
                {"data": "Action audit", "home": "ppa_action_audit", "held_by_harness": "Yes."},
                {"data": "Quick capture", "home": "ScratchFS /inbox",
                 "held_by_harness": "Yes, until promoted into ppa_tasks."}],
            "teaching_point": "A copy of the inbox would be stale the moment it was written. "
                              "The harness reads through MCP and holds only a 20-second read cache."}


@router.post("/read")
async def read(req: ToolReq):
    """Run one read tool live: the raw MCP result beside what the model is shown."""
    if req.name not in READ_TOOLS:
        raise HTTPException(400, f"{req.name} is not a read tool. Read tools: {', '.join(sorted(READ_TOOLS))}")
    workspace.forget_reads()
    try:
        raw = await workspace.call(req.name, req.arguments)
    except WorkspaceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"tool": req.name, "arguments": req.arguments, "raw_mcp_result": raw,
            "model_facing_result": await tools.run(req.name, req.arguments, CONTEXT),
            "difference": "External text is delimited as untrusted content, governed signals are "
                          "added, and a quarantined thread is withheld."}


@router.post("/attempt")
async def attempt(req: ToolReq):
    """Try any tool through the harness. A tool off the allowlist cannot be reached."""
    tier = ALLOWLIST.get(req.name, "never")
    offered = any(item["name"] == req.name for items in workspace.catalogue().values() for item in items)
    if not offered:
        raise HTTPException(404, f"No server offers {req.name}")
    try:
        if tier == "never":
            await workspace.call(req.name, req.arguments)
        result = await tools.run(req.name, req.arguments, CONTEXT)
    except ToolNotAllowed as exc:
        return {"tool": req.name, "offered_by_server": True, "tier": "never", "reached": False,
                "refusal": str(exc), "effects_recorded_by_gateway": await workspace.effects()}
    return {"tool": req.name, "offered_by_server": True, "tier": tier,
            "reached": not result.get("error"), "result": result}


@router.get("/effects")
async def effects():
    """Operator evidence from the gateway: what was really sent or created."""
    return {"effects": await workspace.effects(),
            "note": "This is plain HTTP on the gateway, not an MCP tool, so a model can never call it."}


@router.get("/last_turn")
async def last_turn():
    """The MCP calls the Assistant made on its most recent turn: tool, arguments, result, timing."""
    found = last_turn_calls()
    return {**found, "tiers": {call["tool"]: ALLOWLIST.get(call["tool"], "never") for call in found["calls"]},
            "note": "Kept in memory only, for the last 200 calls. Results longer than 2,500 characters are cut."}
