"""Proactive routines: scheduled work and event triggers.

Nothing here has its own path to the model. A scheduled brief, a meeting that
is about to start and a timer that just fired all enter through ``agent.run``,
the same boundary a typed request uses, and end as a notification.
"""
from __future__ import annotations

from typing import Any

from backend.core import calendar_intel, clock, focus, notifications, scratchfs, store, world
from backend.core.agent import agent
from backend.core.scheduler import scheduler
from backend.core.workspace import WorkspaceError, workspace

MEETING_HORIZON_MINUTES = 30
WATERMARK_KEY = "vip_watermark"
TITLES = {"morning_brief": "Morning brief", "end_of_day_wrap": "End-of-day wrap",
          "weekly_review": "Weekly review", "meeting_prep": "Meeting prep", "vip_alert": "Mail from a VIP",
          "pomodoro": "Session finished"}
REQUESTS = {"morning_brief": "Prepare my morning brief.", "end_of_day_wrap": "Wrap up my day.",
            "weekly_review": "Run my weekly review.",
            "meeting_prep": "Prepare me for the meeting with event ID `{event_id}`.",
            "vip_alert": "A new message arrived from a VIP sender in thread `{thread_id}`. "
                         "Alert me in one line.",
            "pomodoro": "Focus session `{focus_session_id}` finished. Summarise it."}
TRIGGERS = [
    {"kind": "meeting_prep", "label": "Meeting prep",
     "condition": f"a meeting starts within {MEETING_HORIZON_MINUTES} minutes"},
    {"kind": "vip_alert", "label": "VIP alert", "condition": "new mail arrives from a VIP contact"},
]


async def handle(job: dict[str, Any]) -> dict[str, Any]:
    """Run one fired job through the agent and deliver its answer as a notification."""
    kind, payload = job["kind"], job["payload"]
    request = payload.get("request") or REQUESTS[kind].format(**payload)
    body, run_id, pending = "", None, 0
    if kind == "pomodoro":
        focus.complete(payload["focus_session_id"])
    try:
        # A timer must report on time, so its summary never waits on a model.
        outcome = await agent.run(request, thread_id=f"auto-{job['job_id']}", trigger=kind,
                                  responder="scripted" if kind == "pomodoro" else None)
        run_id, pending = outcome["run_id"], len(outcome["pending_actions"])
        body = outcome["answer"] or f"{pending} drafted action(s) are waiting for your approval."
    except Exception as exc:
        if kind != "pomodoro":
            raise
        body = f"Session finished. The summary could not be written ({type(exc).__name__})."
    if kind == "end_of_day_wrap" and scratchfs.session()["status"] == "ACTIVE":
        scratchfs.end_session()
    delivered = notifications.notify(kind, TITLES[kind], body, job_id=job["job_id"], run_id=run_id,
                                     payload={**payload, "pending_actions": pending})
    return {"notification_id": delivered["notification_id"], "run_id": run_id}


async def run_now(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fire one routine immediately, as its schedule or trigger would."""
    if kind not in REQUESTS or kind == "pomodoro":
        raise KeyError(kind)
    job = scheduler.arm(kind, f"{TITLES[kind]} (run now)", clock.now(), payload=payload or {},
                        on_clock="real" if clock.mode() == "real" else "harness")
    return await scheduler.run_inline(job["job_id"])


async def evaluate_triggers() -> dict[str, Any]:
    """Check the event conditions and arm a job for each one that is newly true."""
    now = clock.now()
    on_clock = "real" if clock.mode() == "real" else "harness"
    armed: list[dict[str, Any]] = []
    try:
        for event in await calendar_intel.upcoming_meetings(MEETING_HORIZON_MINUTES):
            job = scheduler.arm("meeting_prep", f"Meeting prep: {event['title']}", now, on_clock=on_clock,
                                payload={"event_id": event["event_id"], "starts_at": event["start"]},
                                dedupe_key=f"meeting_prep:{event['event_id']}:{event['start']}")
            armed += [job] if job else []
        watermark = store.get_meta(WATERMARK_KEY)
        if watermark and clock.localise(watermark) <= now:
            vips = {item["email"] for item in store.contacts() if item["is_vip"]}
            workspace.forget_reads()
            found = await workspace.call("mail_search_threads", {"label": "INBOX", "max_results": 25})
            for thread in found.get("threads", []):
                received = clock.localise(thread["received_at"])
                if thread["from_email"].lower() in vips and clock.localise(watermark) < received <= now:
                    job = scheduler.arm("vip_alert", f"VIP alert: {thread['from_email']}", now,
                                        on_clock=on_clock, payload={"thread_id": thread["thread_id"]},
                                        dedupe_key=f"vip_alert:{thread['thread_id']}")
                    armed += [job] if job else []
        # The first check only sets the baseline: mail that was already there is not new.
        store.set_meta(WATERMARK_KEY, now.isoformat(timespec="seconds"))
    except WorkspaceError as exc:
        return {"checked_at": clock.stamp(), "armed": armed, "error": str(exc)}
    return {"checked_at": clock.stamp(), "armed": armed, "watermark": store.get_meta(WATERMARK_KEY)}


async def simulate_week(days: int = 5) -> dict[str, Any]:
    """Drive the real runtime through working days on an advancing clock.

    Each day plans the top tasks, runs their focus sessions on the harness
    clock, completes what was finished and ends the workday. Every row comes
    from the same functions the assistant uses; nothing is inserted by hand.
    Routines and triggers are paused while it runs, so no model is called.
    """
    from backend.core import runtime, tasks

    if clock.mode() == "real":
        raise RuntimeError("The simulation needs a pinned clock. Use the practice workspace.")
    persona = world.persona()
    work, was_enabled = persona["pomodoro_minutes"], scheduler.automation_enabled()
    scheduler.set_automation(False)
    report = []
    day = clock.today() if clock.today().weekday() < 5 else clock.business_day(clock.today(), 1)
    try:
        for number in range(days):
            opens = clock.at(day, persona["work_start"])
            await runtime.set_clock(opens.isoformat(timespec="minutes"), evaluate=False)
            scratchfs.begin_session()
            plan = await calendar_intel.plan(None, day)
            completed = 0
            for index, block in enumerate(plan["blocks"]):
                await runtime.set_clock(block["start"], evaluate=False)
                began = focus.start(block["task_id"], block["pomodoros"] * work, note="simulated week")
                # Every fourth session is cut short, as real days go.
                cut_short = (number + index) % 4 == 3
                focus.finish_at(began["session"]["session_id"], 0.4 if cut_short else 1.0,
                                "simulated week, cut short" if cut_short else "")
            for task in {block["task_id"] for block in plan["blocks"]}:
                spent = sum(item["actual_minutes"] for item in focus.log(500)
                            if item["task_id"] == task and item["status"] == "COMPLETED")
                if spent >= tasks.get(task)["est_pomodoros"] * work and tasks.get(task)["status"] == "OPEN":
                    tasks.set_status(task, "DONE")
                    completed += 1
            closes = clock.at(day, persona["work_end"])
            await runtime.set_clock(closes.isoformat(timespec="minutes"), evaluate=False)
            ended = scratchfs.end_session()
            report.append({"day": day.isoformat(), "weekday": day.strftime("%A"),
                           "blocks": len(plan["blocks"]), "focus_sessions": len(plan["blocks"]),
                           "completed": completed, "carried_over": len(ended["carried_over"])})
            day = clock.business_day(day, 1)
        # The simulation did the end-of-day work itself, and mail that arrived meanwhile is not new.
        store.execute("UPDATE ppa_schedules SET last_fired_at=? WHERE kind='end_of_day_wrap'",
                      (clock.now().isoformat(timespec="seconds"),))
        store.set_meta(WATERMARK_KEY, clock.now().isoformat(timespec="seconds"))
    finally:
        scheduler.set_automation(was_enabled)
    state = clock.status()
    from backend.core.events import bus

    bus.publish("clock", **state)
    return {"days": report, "clock": state, "automation": "paused while the simulation ran",
            "method": "real planning, focus and workday functions on an advancing practice clock"}


def status() -> dict[str, Any]:
    return {"schedules": scheduler.schedules(), "triggers": TRIGGERS,
            "watermark": store.get_meta(WATERMARK_KEY), "requests": REQUESTS,
            "entry_point": "agent.run, the same boundary as a typed request",
            "pomodoro_responder": "always the scripted responder, so a timer reports on time"}
