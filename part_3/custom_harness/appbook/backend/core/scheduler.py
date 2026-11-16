"""The persistent runtime for timers and scheduled work.

Every job is a row in ``ppa_automation_queue``. A background thread polls the
table and fires what is due, so an app restart re-arms every job from the
database. In the notebook this role is played by ``DBMS_SCHEDULER`` and a queue
worker; here it is a thread and SQLite.

A job moves ``ARMED`` to ``FIRED`` to ``DELIVERED``, or ends ``CANCELLED`` or
``FAILED``. Focus timers run on the real clock. Scheduled routines run on the
harness clock, so a pinned practice clock can be moved to reach them.
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from backend.config import settings
from backend.core import clock, store, world
from backend.core.events import bus

GRACE = timedelta(minutes=30)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
AUTOMATION_KEY = "automation"
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _shift(hhmm: str, minutes: int) -> str:
    base = datetime(2000, 1, 1, int(hhmm[:2]), int(hhmm[3:])) + timedelta(minutes=minutes)
    return base.strftime("%H:%M")


def default_schedules() -> list[dict[str, Any]]:
    """Routine times follow the owner's working hours, not fixed numbers."""
    persona = world.persona()
    return [
        {"schedule_name": "morning_brief", "kind": "morning_brief", "label": "Morning brief",
         "days": "mon,tue,wed,thu,fri", "local_time": _shift(persona["work_start"], -60),
         "request": "Prepare my morning brief."},
        {"schedule_name": "end_of_day_wrap", "kind": "end_of_day_wrap", "label": "End-of-day wrap",
         "days": "mon,tue,wed,thu,fri", "local_time": persona["work_end"],
         "request": "Wrap up my day."},
        {"schedule_name": "weekly_review", "kind": "weekly_review", "label": "Weekly review",
         "days": "fri", "local_time": _shift(persona["work_end"], -90),
         "request": "Run my weekly review."},
    ]


def first_occurrence(days: str, local_time: str, after: datetime) -> datetime:
    """The first moment strictly after ``after`` that matches the weekday set and time."""
    wanted = {WEEKDAYS.index(item) for item in days.split(",")}
    day = after.astimezone(clock.tz()).date()
    for _ in range(15):
        moment = clock.at(day, local_time)
        if day.weekday() in wanted and moment > after:
            return moment
        day += timedelta(days=1)
    raise ValueError(f"No occurrence found for {days} {local_time}")


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    from backend.core import notifications

    fires = datetime.fromisoformat(item["fires_at"])
    reference = datetime.now(timezone.utc) if item["clock"] == "real" else clock.now()
    return {**item, "payload": store.loads(item["payload"], {}),
            "seconds_remaining": max(0, round((fires - reference).total_seconds()))
            if item["state"] == "ARMED" else None,
            "notification": notifications.get(item["notification_id"])}


class Scheduler:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._handlers: dict[str, Handler] = {}
        self._triggers: Callable[[], Awaitable[Any]] | None = None
        self._last_trigger_check = time.monotonic()
        self.rearmed: list[str] = []
        self.started_at: str | None = None

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def watch(self, evaluate: Callable[[], Awaitable[Any]]) -> None:
        """Install the coroutine that checks event triggers."""
        self._triggers = evaluate

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Re-arm what the database holds, then start polling."""
        self.rearm()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ppa-scheduler", daemon=True)
            self._thread.start()
        self.started_at = store.real_now()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def rearm(self) -> list[str]:
        """Jobs survive a restart: armed jobs stay armed, interrupted ones are armed again."""
        stamp = store.real_now()
        store.execute("UPDATE ppa_automation_queue SET state='ARMED',fired_at=NULL,rearmed_at=? "
                      "WHERE state='FIRED'", (stamp,), trace=False)
        store.execute("UPDATE ppa_automation_queue SET rearmed_at=? WHERE state='ARMED'", (stamp,),
                      trace=False)
        self.rearmed = [item["job_id"] for item in store.rows(
            "SELECT job_id FROM ppa_automation_queue WHERE state='ARMED' AND schedule_name IS NULL",
            trace=False)]
        self.sync_schedules()
        return self.rearmed

    # ── Jobs ─────────────────────────────────────────────────────────────────

    def arm(self, kind: str, label: str, fires_at: datetime, *, on_clock: str = "real",
            payload: dict | None = None, task_id: str | None = None, dedupe_key: str | None = None,
            schedule_name: str | None = None) -> dict[str, Any] | None:
        """Store one job. Returns ``None`` when a job with the same dedupe key already exists."""
        if dedupe_key and store.row("SELECT 1 FROM ppa_automation_queue WHERE dedupe_key=?",
                                    (dedupe_key,), trace=False):
            return None
        job_id = store.new_id("JOB")
        store.execute(
            "INSERT INTO ppa_automation_queue(job_id,kind,label,task_id,schedule_name,payload,clock,"
            "fires_at,state,dedupe_key,created_at) VALUES (?,?,?,?,?,?,?,?,'ARMED',?,?)",
            (job_id, kind, label, task_id, schedule_name, store.dumps(payload or {}), on_clock,
             fires_at.isoformat(timespec="seconds"), dedupe_key, store.real_now()))
        return self._announce(job_id)

    def cancel(self, job_id: str, reason: str = "cancelled by the user") -> dict[str, Any] | None:
        changed = store.execute(
            "UPDATE ppa_automation_queue SET state='CANCELLED',finished_at=?,error=? "
            "WHERE job_id=? AND state='ARMED'", (store.real_now(), reason, job_id))
        return self._announce(job_id) if changed else None

    def job(self, job_id: str) -> dict[str, Any] | None:
        found = store.row("SELECT * FROM ppa_automation_queue WHERE job_id=?", (job_id,), trace=False)
        return _shape(found) if found else None

    def jobs(self, limit: int = 60) -> list[dict[str, Any]]:
        found = store.rows(
            "SELECT * FROM ppa_automation_queue ORDER BY (state='ARMED') DESC, rowid DESC LIMIT ?",
            (limit,))
        return [_shape(item) for item in found]

    def _announce(self, job_id: str) -> dict[str, Any]:
        shaped = self.job(job_id)
        bus.publish("timer", **shaped)
        return shaped

    # ── Schedules ────────────────────────────────────────────────────────────

    def automation_enabled(self) -> bool:
        return store.get_meta(AUTOMATION_KEY, "on") == "on"

    def set_automation(self, enabled: bool) -> bool:
        store.set_meta(AUTOMATION_KEY, "on" if enabled else "off")
        self.sync_schedules()
        return enabled

    def schedules(self) -> list[dict[str, Any]]:
        return [{**item, "enabled": bool(item["enabled"])}
                for item in store.rows("SELECT * FROM ppa_schedules ORDER BY rowid")]

    def set_schedule(self, name: str, *, enabled: bool | None = None,
                     local_time: str | None = None) -> dict[str, Any]:
        if store.row("SELECT 1 FROM ppa_schedules WHERE schedule_name=?", (name,)) is None:
            raise KeyError(name)
        if enabled is not None:
            store.execute("UPDATE ppa_schedules SET enabled=? WHERE schedule_name=?", (int(enabled), name))
        if local_time:
            clock.at(clock.today(), local_time)       # validates HH:MM
            store.execute("UPDATE ppa_schedules SET local_time=? WHERE schedule_name=?", (local_time, name))
        self.sync_schedules()
        return next(item for item in self.schedules() if item["schedule_name"] == name)

    def sync_schedules(self) -> None:
        """Arm each enabled schedule at its next occurrence on the current clock.

        Called at start, after a routine fires and whenever the clock moves. An
        occurrence missed by more than the grace period is skipped, not replayed.
        """
        for item in default_schedules():
            store.execute(
                "INSERT OR IGNORE INTO ppa_schedules(schedule_name,kind,label,days,local_time,request) "
                "VALUES (?,?,?,?,?,?)", tuple(item.values()), trace=False)
        now = clock.now()
        on_clock = "real" if clock.mode() == "real" else "harness"
        for item in self.schedules():
            armed = store.row("SELECT job_id FROM ppa_automation_queue WHERE schedule_name=? "
                              "AND state='ARMED'", (item["schedule_name"],), trace=False)
            if not item["enabled"] or not self.automation_enabled():
                if armed:
                    self.cancel(armed["job_id"], "schedule or automation switched off")
                continue
            last = datetime.fromisoformat(item["last_fired_at"]) if item["last_fired_at"] else None
            if last and last > now:                   # the clock was moved back past it
                last = None
                store.execute("UPDATE ppa_schedules SET last_fired_at=NULL WHERE schedule_name=?",
                              (item["schedule_name"],), trace=False)
            after = max(now - GRACE, last) if last else now - GRACE
            fires = first_occurrence(item["days"], item["local_time"], after)
            if armed:
                store.execute("UPDATE ppa_automation_queue SET fires_at=?,clock=? WHERE job_id=?",
                              (fires.isoformat(timespec="seconds"), on_clock, armed["job_id"]), trace=False)
                self._announce(armed["job_id"])
            else:
                self.arm(item["kind"], item["label"], fires, on_clock=on_clock,
                         payload={"request": item["request"]}, schedule_name=item["schedule_name"])

    # ── The loop ─────────────────────────────────────────────────────────────

    def _due(self) -> list[dict[str, Any]]:
        real, harness = datetime.now(timezone.utc), clock.now()
        found = store.rows("SELECT * FROM ppa_automation_queue WHERE state='ARMED'", trace=False)
        return [item for item in found
                if datetime.fromisoformat(item["fires_at"]) <= (real if item["clock"] == "real" else harness)]

    def _run(self) -> None:
        while not self._stop.wait(settings.scheduler_poll_seconds):
            try:
                for item in self._due():
                    self.fire(item["job_id"])
                if self._triggers and time.monotonic() - self._last_trigger_check \
                        >= settings.trigger_poll_seconds:
                    self.check_triggers()
            except Exception as exc:          # the loop must outlive one bad job
                bus.publish("scheduler_error", error=str(exc)[:300])

    def check_triggers(self) -> None:
        """Ask the event loop to evaluate the event triggers."""
        self._last_trigger_check = time.monotonic()
        loop = bus.loop
        if self._triggers and loop is not None and loop.is_running() and self.automation_enabled():
            asyncio.run_coroutine_threadsafe(self._triggers(), loop)

    def fire(self, job_id: str) -> bool:
        """Claim one armed job and hand it to its handler on the server's event loop."""
        claimed = store.execute(
            "UPDATE ppa_automation_queue SET state='FIRED',fired_at=? WHERE job_id=? AND state='ARMED'",
            (store.real_now(), job_id))
        loop = bus.loop
        if not claimed or loop is None:
            return False
        job = self._announce(job_id)
        asyncio.run_coroutine_threadsafe(self._handle(job), loop)
        return True

    async def run_inline(self, job_id: str) -> dict[str, Any]:
        """Fire one job now and wait for it: the path behind every "run now" button."""
        claimed = store.execute(
            "UPDATE ppa_automation_queue SET state='FIRED',fired_at=? WHERE job_id=? AND state='ARMED'",
            (store.real_now(), job_id))
        if not claimed:
            raise LookupError(f"{job_id} is not armed")
        await self._handle(self._announce(job_id))
        return self.job(job_id)

    async def _handle(self, job: dict[str, Any]) -> None:
        handler = self._handlers.get(job["kind"])
        try:
            if handler is None:
                raise RuntimeError(f"No handler is registered for {job['kind']}")
            outcome = await handler(job)
            store.execute(
                "UPDATE ppa_automation_queue SET state='DELIVERED',finished_at=?,notification_id=?,"
                "run_id=? WHERE job_id=?",
                (store.real_now(), outcome.get("notification_id"), outcome.get("run_id"), job["job_id"]))
        except Exception as exc:
            store.execute("UPDATE ppa_automation_queue SET state='FAILED',finished_at=?,error=? "
                          "WHERE job_id=?", (store.real_now(), str(exc)[:500], job["job_id"]))
        if job["schedule_name"]:
            store.execute("UPDATE ppa_schedules SET last_fired_at=? WHERE schedule_name=?",
                          (job["fires_at"], job["schedule_name"]))
            self.sync_schedules()
        self._announce(job["job_id"])

    def status(self) -> dict[str, Any]:
        states = store.rows("SELECT state, COUNT(*) AS total FROM ppa_automation_queue GROUP BY state")
        return {"implementation": "background thread polling ppa_automation_queue "
                                  "(DBMS_SCHEDULER and a queue worker in the notebook)",
                "running": bool(self._thread and self._thread.is_alive()),
                "poll_seconds": settings.scheduler_poll_seconds,
                "trigger_poll_seconds": settings.trigger_poll_seconds,
                "automation_enabled": self.automation_enabled(),
                "started_at": self.started_at, "rearmed_at_start": self.rearmed,
                "states": {item["state"]: item["total"] for item in states},
                "grace_minutes": int(GRACE.total_seconds() // 60)}


scheduler = Scheduler()
