"""Chapter 6: inbox triage and task extraction."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import approval, clock, inbox, tasks, tools
from backend.routers.deps import ready
from backend.schemas import ExtractReq

router = APIRouter(prefix="/api/inbox_triage", tags=["inbox_triage"], dependencies=[Depends(ready)])


def _context() -> tools.ToolContext:
    return tools.ToolContext(thread_id="chapter-inbox-triage", session_id=clock.session_id(), origin="manual")


def _row(row: dict) -> dict:
    """The human view. A quarantined body is kept back until a person asks to see it."""
    shown = {key: value for key, value in row.items() if key not in {"body", "participants"}}
    shown["snippet"] = "" if row["category"] == "quarantine" else " ".join(row["body"].split())[:220]
    return shown


@router.get("/status")
async def status():
    result = await inbox.triage()
    rows = result["rows"]
    unknown = [row for row in rows if row["trust"] == "unknown"]
    return {"chapter": "Inbox triage and task extraction", "as_of": result["as_of"],
            "window": result["window"], "counts": result["counts"], "rows": [_row(row) for row in rows],
            "first": rows[0]["thread_id"] if rows else None,
            "unknown_senders": {"threads": len(unknown),
                                "flagged_by_tripwire": sum(bool(row["injection_patterns"]) for row in unknown),
                                "passed_the_tripwire": [row["thread_id"] for row in unknown
                                                        if not row["injection_patterns"]]},
            "tripwire": approval.TRIPWIRE_FINDING, "rule": result["rule"],
            "order": "attention rank, then newest first",
            "open_tasks": len(tasks.governed(include_snoozed=True))}


@router.get("/thread/{thread_id}")
async def thread(thread_id: str):
    """One thread for a person to read. The model never receives this view."""
    found = await inbox.thread(thread_id)
    if found is None:
        raise HTTPException(404, "No such thread")
    return {**found, "model_facing": inbox.for_model(found, body=True),
            "warning": "Quarantined: instruction-like text from an unknown sender. It is shown to "
                       "you, not to the model." if found["category"] == "quarantine" else None}


@router.post("/extract")
async def extract(req: ExtractReq):
    """Turn actionable rows into tasks and unsent drafts, through the same trusted tools."""
    result = await inbox.triage()
    chosen = [row for row in result["rows"] if not req.thread_ids or row["thread_id"] in req.thread_ids]
    created, suppressed, drafts = [], [], []
    for row in chosen:
        proposal = row.get("proposal")
        if not proposal:
            continue
        made = await tools.run("task_add", {**proposal["task"], "reason": f"Triage: {row['reason']}."},
                               _context())
        entry = {"thread_id": row["thread_id"], "task_id": made.get("task_id"), "status": made.get("status"),
                 "title": proposal["task"]["title"]}
        (created if made.get("status") == "created" else suppressed).append(entry)
        if proposal["draft"] and made.get("status") == "created":
            saved = await tools.run("mail_create_draft", {
                **proposal["draft"], "reason": "Holding reply saved as a draft; nothing is sent."},
                _context())
            drafts.append({"thread_id": row["thread_id"], "draft_id": saved.get("draft_id"),
                           "to": proposal["draft"]["to"], "sent": False})
    return {"created": created, "suppressed_duplicates": suppressed, "drafts": drafts,
            "tracked": [{"thread_id": row["thread_id"], "task_id": row["tracked_task_id"]}
                        for row in chosen if row["category"] == "tracked"],
            "quarantined": [row["thread_id"] for row in chosen if row["category"] == "quarantine"],
            "archived": sum(row["category"] == "archive" for row in chosen),
            "rule": "An open task whose source is the thread suppresses a second one."}
