"""The running to-do list. ``ppa_tasks`` is its only home.

Mail, calendar and notes are read through MCP on demand; tasks are the one
thing the harness owns outright. Order, urgency, slipping and staleness come
from the shared policy, never from this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import policy

from backend.core import clock, store
from backend.core.memory import content_hash

FADE_AFTER_DAYS = 2
SOURCE_TYPES = ("mail", "notes", "calendar", "chat", "capture")


def _shape(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    snoozed = bool(item["snoozed_until"]) and datetime.fromisoformat(item["snoozed_until"]) > now
    return {**item, "urgent": policy.is_urgent(item, now), "snoozed": snoozed}


def everything() -> list[dict[str, Any]]:
    """Every task row, in the shape the shared policy expects."""
    return store.rows("SELECT * FROM ppa_tasks ORDER BY rowid")


def get(task_id: str) -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_tasks WHERE task_id=?", (task_id,))
    return _shape(found, clock.now()) if found else None


def governed(*, include_snoozed: bool = False) -> list[dict[str, Any]]:
    """Open tasks in governed order: urgent first, then priority, then due date."""
    now = clock.now()
    ordered = [_shape(item, now) for item in policy.task_order(everything(), now)]
    return [item for item in ordered if include_snoozed or not item["snoozed"]]


def recently_done() -> list[dict[str, Any]]:
    """Done items stay in view for two days, then fade."""
    now = clock.now()
    cutoff = now - timedelta(days=FADE_AFTER_DAYS)
    return [_shape(item, now) for item in everything()
            if item["status"] == "DONE" and datetime.fromisoformat(item["completed_at"]) > cutoff]


def faded() -> list[dict[str, Any]]:
    now = clock.now()
    cutoff = now - timedelta(days=FADE_AFTER_DAYS)
    return [_shape(item, now) for item in everything()
            if item["status"] == "DONE" and datetime.fromisoformat(item["completed_at"]) <= cutoff]


def tracking(source_ref: str | None) -> dict[str, Any] | None:
    """The open task that already covers a thread, page or event."""
    if not source_ref:
        return None
    return store.row("SELECT * FROM ppa_tasks WHERE status='OPEN' AND source_ref=? ORDER BY rowid",
                     (source_ref,))


def add(title: str, *, priority: int = 3, due_at: str | None = None, est_pomodoros: int = 1,
        source_type: str = "chat", source_ref: str | None = None) -> dict[str, Any]:
    """Create a task, unless an open task already covers the same source or wording."""
    title = " ".join(title.split())
    if not title:
        raise ValueError("A task needs a title")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {', '.join(SOURCE_TYPES)}")
    if due_at:
        due_at = clock.localise(due_at).isoformat(timespec="minutes")
    digest = content_hash(title)
    existing = tracking(source_ref) or store.row(
        "SELECT * FROM ppa_tasks WHERE status='OPEN' AND content_hash=?", (digest,))
    if existing:
        return {"status": "already_tracked", "task": _shape(existing, clock.now()),
                "message": f"Open task {existing['task_id']} already covers this. No duplicate was created."}
    stamp = clock.stamp()
    item = {"task_id": store.new_id("T"), "title": title, "status": "OPEN",
            "priority": min(max(int(priority), 1), 4), "due_at": due_at,
            "est_pomodoros": min(max(int(est_pomodoros), 1), 8), "source_type": source_type,
            "source_ref": source_ref, "carry_over_count": 0, "planned_for": None,
            "snoozed_until": None, "content_hash": digest, "created_at": stamp,
            "touched_at": stamp, "completed_at": None}
    store.execute("INSERT INTO ppa_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(item.values()))
    return {"status": "created", "task": _shape(item, clock.now())}


def update(task_id: str, **changes: Any) -> dict[str, Any]:
    allowed = {"title", "priority", "due_at", "est_pomodoros", "planned_for", "snoozed_until"}
    fields = {key: value for key, value in changes.items() if key in allowed and value is not None}
    if get(task_id) is None:
        raise KeyError(task_id)
    if "title" in fields:
        fields["title"] = " ".join(str(fields["title"]).split())
        fields["content_hash"] = content_hash(fields["title"])
    for key in ("due_at", "snoozed_until"):
        if fields.get(key):
            fields[key] = clock.localise(fields[key]).isoformat(timespec="minutes")
    fields["touched_at"] = clock.stamp()
    assignments = ",".join(f"{key}=?" for key in fields)
    store.execute(f"UPDATE ppa_tasks SET {assignments} WHERE task_id=?", (*fields.values(), task_id))
    return get(task_id)


def clear(task_id: str, field: str) -> dict[str, Any]:
    """Remove a due date or a snooze."""
    if field not in {"due_at", "snoozed_until", "planned_for"}:
        raise ValueError(field)
    store.execute(f"UPDATE ppa_tasks SET {field}=NULL,touched_at=? WHERE task_id=?",
                  (clock.stamp(), task_id))
    return get(task_id)


def set_status(task_id: str, status: str) -> dict[str, Any]:
    if get(task_id) is None:
        raise KeyError(task_id)
    stamp = clock.stamp()
    store.execute("UPDATE ppa_tasks SET status=?,touched_at=?,completed_at=? WHERE task_id=?",
                  (status, stamp, stamp if status == "DONE" else None, task_id))
    return get(task_id)


def carry_over(day: str) -> list[dict[str, Any]]:
    """Count one more slip for every task planned for ``day`` that is still open."""
    slipped = store.rows("SELECT * FROM ppa_tasks WHERE status='OPEN' AND planned_for=?", (day,))
    for item in slipped:
        store.execute("UPDATE ppa_tasks SET carry_over_count=carry_over_count+1,planned_for=NULL "
                      "WHERE task_id=?", (item["task_id"],))
    return [get(item["task_id"]) for item in slipped]


def health() -> dict[str, Any]:
    """Slipping and stale tasks, as the shared policy defines them."""
    now = clock.now()
    rows = everything()
    return {"slipping": [_shape(item, now) for item in policy.slipping_tasks(rows)],
            "stale": [_shape(item, now) for item in policy.stale_tasks(rows, now)],
            "faded_done": faded(),
            "definitions": {"slipping": "open and carried over at least twice",
                            "stale": "open, undated and untouched for 30 days",
                            "faded": f"done more than {FADE_AFTER_DAYS} days ago"}}
