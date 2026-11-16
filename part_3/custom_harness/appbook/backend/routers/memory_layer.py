"""Chapter 4: memory and the workday scratch pad."""
from fastapi import APIRouter, Depends, HTTPException

import policy

from backend.core import clock, scratchfs, store, tasks, world
from backend.core.memory import DEFAULT_TTL_DAYS, expires_in_days, memory_provider
from backend.core.workspace import workspace
from backend.routers.deps import ready
from backend.schemas import (CaptureReq, MemoryReq, MemoryUpdateReq, PlanReq, QueryReq, ScratchFlagReq,
                             ScratchWriteReq)

router = APIRouter(prefix="/api/memory_layer", tags=["memory_layer"], dependencies=[Depends(ready)])


def _decay() -> dict:
    now = clock.now()
    health = tasks.health()
    memories = [item for items in memory_provider.list().values() for item in items]
    return {"as_of": clock.stamp(),
            "faded_done": health["faded_done"], "drop_candidates": health["stale"],
            "slipping": health["slipping"],
            "expiring": sorted(
                [{**item, "expires_in_days": expires_in_days(item, now)} for item in memories
                 if item["status"] == "ACTIVE" and item["expires_at"]],
                key=lambda item: item["expires_in_days"])[:12],
            "expired": [item for item in memories if item["status"] == "EXPIRED"],
            "rules": {"done items": f"fade {tasks.FADE_AFTER_DAYS} days after completion",
                      "stale tasks": "open, undated and untouched for 30 days become drop candidates",
                      "memories": {kind: ("kept until changed" if days is None else f"{days} days")
                                   for kind, days in DEFAULT_TTL_DAYS.items()}}}


@router.get("/status")
async def status():
    grouped = memory_provider.list()
    return {"chapter": "Memory and the workday scratch pad", **memory_provider.status(),
            "memories": grouped, "standing": memory_provider.standing(),
            "people": store.contacts()[:12], "scratch": scratchfs.status(), "decay": _decay(),
            "sessions": store.rows("SELECT * FROM ppa_agent_sessions ORDER BY rowid DESC LIMIT 10"),
            "clock": clock.status()}


@router.post("/write")
async def write(req: MemoryReq):
    return memory_provider.write(req.memory_type, req.content, ttl_days=req.ttl_days,
                                 metadata={"source": "appbook"})


@router.post("/recall")
async def recall(req: QueryReq):
    return {"query": req.query, "recalled": memory_provider.recall(req.query),
            "standing": memory_provider.standing(),
            "method": "keyword overlap; standing preferences and guidelines always apply"}


@router.patch("/{memory_id}")
async def update(memory_id: str, req: MemoryUpdateReq):
    try:
        return memory_provider.update(memory_id, req.content, req.ttl_days)
    except KeyError as exc:
        raise HTTPException(404, "No such memory") from exc


@router.delete("/{memory_id}")
async def delete(memory_id: str):
    return {"memory_id": memory_id, "deleted": memory_provider.delete(memory_id)}


@router.post("/capture")
async def capture(req: CaptureReq):
    from backend.core import focus

    return focus.distraction(req.text)


@router.get("/plan")
async def read_plan():
    session = scratchfs.session()
    return {"session_id": session["session_id"], "path": scratchfs.PLAN_PATH, "content": session["plan"]}


@router.put("/plan")
async def write_plan(req: PlanReq):
    return scratchfs.begin_session().write(scratchfs.PLAN_PATH, req.content, kind="plan")


@router.post("/scratch/write")
async def scratch_write(req: ScratchWriteReq):
    try:
        return scratchfs.begin_session().write(req.path, req.content, promote_on_end=req.promote_on_end,
                                               promote_target=req.promote_target)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/scratch/flag")
async def scratch_flag(req: ScratchFlagReq):
    try:
        return scratchfs.begin_session().flag(req.path, promote=req.promote, target=req.target)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"No such file: {exc}") from exc


@router.post("/scratch/delete")
async def scratch_delete(req: ScratchFlagReq):
    return {"path": req.path, "deleted": scratchfs.begin_session().delete(req.path)}


@router.post("/session/start")
async def start_session():
    scratchfs.begin_session()
    return scratchfs.session()


@router.post("/session/end")
async def end_session():
    return scratchfs.end_session()


@router.get("/decay")
async def decay():
    return _decay()


@router.post("/decay/sweep")
async def sweep():
    expired = memory_provider.sweep()
    return {"expired_now": expired, **_decay()}


@router.post("/commitments/scan")
async def scan_commitments():
    """Read the notes through MCP and remember the actions that belong to the owner."""
    found = await workspace.call("notes_search", {"query": ""})
    written = []
    for page in found.get("pages", []):
        body = (await workspace.call("notes_get_page", {"page_id": page["page_id"]})).get("page", {})
        for action in policy.extract_actions(body.get("body", ""), world.owner_first_name()):
            written.append(memory_provider.write("commitment", action, metadata={
                "source": "notes", "page_id": page["page_id"], "page_title": page["title"]}))
    return {"pages_read": len(found.get("pages", [])), "commitments": written,
            "new": sum(not item["deduplicated"] for item in written),
            "rule": "Lines of the form ACTION (name): text that name the owner."}
