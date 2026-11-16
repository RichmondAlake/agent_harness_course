"""The weekly review and the end-of-day wrap, computed from what the harness recorded.

Nothing here is seeded. An empty period returns an empty review and says so;
the numbers fill in as tasks are created, planned, worked on and completed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import policy

from backend.core import calendar_intel, clock, focus, scratchfs, store, tasks

PERIOD_DAYS = 7


def _inside(value: str | None, first: datetime, last: datetime) -> bool:
    return bool(value) and first <= clock.localise(value) <= last


def weekly() -> dict[str, Any]:
    """Planned versus done, where time went, what keeps slipping and what to drop."""
    last = clock.now()
    first = (last - timedelta(days=PERIOD_DAYS)).replace(hour=0, minute=0, second=0)
    every = tasks.everything()
    titles = {item["task_id"]: item["title"] for item in every}
    sessions = focus.between(first, last)
    worked = {item["task_id"] for item in sessions if item["task_id"]}
    planned = [item for item in every if item["status"] != "DROPPED" and (
        _inside(item["due_at"], first, last) or _inside(item["completed_at"], first, last)
        or item["task_id"] in worked
        or (item["planned_for"] and first.date().isoformat() <= item["planned_for"] <= last.date().isoformat())
        or item["carry_over_count"] > 0)]
    done = [item for item in planned if item["status"] == "DONE"
            and _inside(item["completed_at"], first, last)]
    summary = policy.focus_summary(sessions)
    time_by_task = sorted(
        [{"task_id": key, "title": titles.get(key, "Unplanned time" if key == "unplanned" else key),
          "minutes": minutes} for key, minutes in summary["minutes_by_task"].items()],
        key=lambda item: -item["minutes"])
    gated = store.rows("SELECT state, COUNT(*) AS total FROM ppa_action_audit "
                       "WHERE tier='approval' GROUP BY state")
    slipping = policy.slipping_tasks(every)
    stale = policy.stale_tasks(every, last)
    return {
        "period": {"from": first.isoformat(timespec="minutes"), "to": last.isoformat(timespec="minutes"),
                   "days": PERIOD_DAYS, "rule": f"the last {PERIOD_DAYS} days on the harness clock"},
        "empty": not planned and not sessions,
        "planned_vs_done": {"planned": len(planned), "done": len(done),
                            "percent": round(len(done) / len(planned) * 100) if planned else 0,
                            "done_tasks": [{"task_id": item["task_id"], "title": item["title"]} for item in done],
                            "open_tasks": [{"task_id": item["task_id"], "title": item["title"],
                                            "carry_over_count": item["carry_over_count"]}
                                           for item in planned if item["status"] == "OPEN"]},
        "focus": {key: summary[key] for key in ("sessions", "interrupted", "planned_minutes",
                                                "actual_minutes", "completion_percent")},
        "time_by_task": time_by_task,
        "slipping": [{"task_id": item["task_id"], "title": item["title"],
                      "carry_over_count": item["carry_over_count"]} for item in slipping],
        "drop_candidates": [{"task_id": item["task_id"], "title": item["title"],
                             "touched_at": item["touched_at"]} for item in stale],
        "gated_actions": {item["state"]: item["total"] for item in gated},
        "definitions": {"slipping": "open and carried over at least twice",
                        "drop": "open, undated and untouched for 30 days"},
    }


async def end_of_day() -> dict[str, Any]:
    """Done, carried over and tomorrow's first block."""
    now = clock.now()
    today = now.date().isoformat()
    every = tasks.everything()
    done = [item for item in every if item["status"] == "DONE" and (item["completed_at"] or "")[:10] == today]
    carried = [item for item in every if item["status"] == "OPEN" and item["planned_for"] == today]
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=clock.tz())
    sessions = focus.between(start, start + timedelta(days=1))
    tomorrow = clock.business_day(now.date(), 1)
    overview = await calendar_intel.overview(tomorrow)
    queue = [item for item in tasks.governed() if item["task_id"] not in {row["task_id"] for row in done}]
    first_slot = overview["free_slots"][0] if overview["free_slots"] else None
    session = scratchfs.session()
    return {
        "day": today, "weekday": now.strftime("%A"),
        "done": [{"task_id": item["task_id"], "title": item["title"]} for item in done],
        "carried_over": [{"task_id": item["task_id"], "title": item["title"],
                          "carry_over_count": item["carry_over_count"]} for item in carried],
        "focus": policy.focus_summary(sessions),
        "tomorrow": {"day": tomorrow.isoformat(), "weekday": tomorrow.strftime("%A"),
                     "first_free_slot": first_slot,
                     "first_task": {"task_id": queue[0]["task_id"], "title": queue[0]["title"]}
                     if queue else None,
                     "meetings": len([item for item in overview["events"] if item["kind"] == "meeting"])},
        "notes_marked_for_promotion": [{"path": item["path"], "target": item["promote_target"]}
                                       for item in session["files"]
                                       if item["promote_on_end"] and item["promotion_state"] == "N"],
        "session": {"session_id": session["session_id"], "status": session["status"]},
    }
