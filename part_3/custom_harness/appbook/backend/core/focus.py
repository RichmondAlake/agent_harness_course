"""Focus sessions: a real Pomodoro runtime.

Starting a session writes a ``ppa_focus_sessions`` row and arms a one-shot job
on the real clock. The job survives an app restart because it lives in the
database. Distractions captured while a session runs land in the scratch inbox
and are surfaced when the session ends.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import policy

from backend.core import clock, scratchfs, store, tasks, world
from backend.core.events import bus
from backend.core.scheduler import scheduler

MIN_MINUTES, MAX_MINUTES = 5, 90       # what the model-facing tool may ask for


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    task = tasks.get(item["task_id"]) if item["task_id"] else None
    remaining = None
    if item["status"] == "RUNNING":
        ends = datetime.fromisoformat(item["real_ends_at"])
        remaining = max(0, round((ends - datetime.now(timezone.utc)).total_seconds()))
    return {**item, "compressed": bool(item["compressed"]), "task_title": task["title"] if task else None,
            "seconds_remaining": remaining}


def get(session_id: str) -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_focus_sessions WHERE session_id=?", (session_id,))
    return _shape(found) if found else None


def running() -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_focus_sessions WHERE status='RUNNING' ORDER BY rowid DESC")
    return _shape(found) if found else None


def start(task_id: str | None = None, minutes: int | None = None, *,
          real_seconds: int | None = None, note: str = "") -> dict[str, Any]:
    """Start one session. ``real_seconds`` compresses the timer for a demonstration."""
    current = running()
    if current:
        return {"status": "already_running", "session": current,
                "message": "A focus session is already running. Stop it before starting another."}
    if task_id and tasks.get(task_id) is None:
        raise KeyError(task_id)
    planned = int(minutes or world.persona()["pomodoro_minutes"])
    seconds = int(real_seconds or planned * 60)
    began = datetime.now(timezone.utc)
    ends = began + timedelta(seconds=seconds)
    session_id = store.new_id("FS")
    title = tasks.get(task_id)["title"] if task_id else "unplanned focus"
    job = scheduler.arm("pomodoro", f"Focus: {title}", ends, on_clock="real", task_id=task_id,
                        payload={"focus_session_id": session_id})
    try:
        store.execute(
            "INSERT INTO ppa_focus_sessions(session_id,task_id,workday_session_id,planned_minutes,"
            "actual_minutes,status,started_at,note,real_started_at,real_ends_at,real_seconds,compressed,job_id) "
            "VALUES (?,?,?,?,0,'RUNNING',?,?,?,?,?,?,?)",
            (session_id, task_id, scratchfs.begin_session().session_id, planned, clock.stamp(), note,
             began.isoformat(timespec="seconds"), ends.isoformat(timespec="seconds"), seconds,
             int(seconds != planned * 60), job["job_id"]))
    except Exception:
        scheduler.cancel(job["job_id"], "the focus session could not be stored")
        raise
    if task_id:
        tasks.update(task_id, planned_for=clock.today().isoformat())
    session = get(session_id)
    bus.publish("focus", event="started", **session)
    return {"status": "started", "session": session, "job": job}


def _finish(session_id: str, status: str, fraction: float, note: str = "") -> dict[str, Any]:
    current = get(session_id)
    if current is None:
        raise KeyError(session_id)
    if current["status"] != "RUNNING":
        return current
    actual = round(current["planned_minutes"] * min(max(fraction, 0.0), 1.0))
    ended = clock.localise(current["started_at"]) + timedelta(minutes=actual)
    store.execute(
        "UPDATE ppa_focus_sessions SET status=?,actual_minutes=?,ended_at=?,"
        "note=CASE WHEN ?='' THEN note ELSE ? END WHERE session_id=?",
        (status, actual, ended.isoformat(timespec="seconds"), note, note, session_id))
    session = get(session_id)
    bus.publish("focus", event=status.lower(), **session)
    return session


def complete(session_id: str) -> dict[str, Any]:
    """The timer fired: the session ran its full length."""
    return _finish(session_id, "COMPLETED", 1.0)


def stop(reason: str = "") -> dict[str, Any]:
    """Stop the running session early and cancel its timer."""
    current = running()
    if current is None:
        return {"status": "not_running", "message": "No focus session is running."}
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(current["real_started_at"])).total_seconds()
    session = _finish(current["session_id"], "INTERRUPTED", elapsed / current["real_seconds"], reason)
    if current["job_id"]:
        scheduler.cancel(current["job_id"], "the focus session was stopped early")
    return {"status": "stopped", "session": session, "distractions": scratchfs.distractions(session["session_id"])}


def finish_at(session_id: str, fraction: float, note: str = "") -> dict[str, Any]:
    """End a session on the harness clock instead of waiting for its timer."""
    current = get(session_id)
    session = _finish(session_id, "COMPLETED" if fraction >= 1 else "INTERRUPTED", fraction, note)
    if current and current["job_id"]:
        scheduler.cancel(current["job_id"], "ended on the harness clock, not by the timer")
    return session


def distraction(text: str) -> dict[str, Any]:
    """Park a thought without leaving the session. It comes back at the break."""
    current = running()
    captured = scratchfs.capture(text, kind="distraction" if current else "capture",
                                 focus_session_id=current["session_id"] if current else None)
    bus.publish("focus", event="distraction", session_id=captured["focus_session_id"], text=text)
    return captured


def log(limit: int = 50) -> list[dict[str, Any]]:
    return [_shape(item) for item in store.rows(
        "SELECT * FROM ppa_focus_sessions ORDER BY rowid DESC LIMIT ?", (limit,))]


def between(first: datetime, last: datetime) -> list[dict[str, Any]]:
    found = store.rows("SELECT * FROM ppa_focus_sessions WHERE status<>'RUNNING' ORDER BY rowid")
    return [_shape(item) for item in found if first <= clock.localise(item["started_at"]) <= last]


def status() -> dict[str, Any]:
    persona = world.persona()
    finished = [item for item in log(200) if item["status"] != "RUNNING"]
    return {"running": running(), "log": log(30), "summary": policy.focus_summary(finished),
            "defaults": {"pomodoro_minutes": persona["pomodoro_minutes"],
                         "break_minutes": persona["break_minutes"]},
            "tool_limits": {"min_minutes": MIN_MINUTES, "max_minutes": MAX_MINUTES},
            "timer": "one-shot job on the real clock, stored in ppa_automation_queue"}
