"""Calendar intelligence: free time, load, time-blocking and meeting preparation.

Events are read through MCP on demand. What counts as free, over-booked or a
broken meeting rule is decided by the shared policy with the owner's persona.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import policy

from backend.core import clock, scratchfs, store, tasks, world
from backend.core.workspace import WorkspaceError, workspace

PREP_WINDOW_DAYS = 14
# The practice calendar has two layers, and every event names its own in ``source``.
SESSION_PREFIX = "Working session: "
LAYERS = {
    "invitation": "Derived from an invitation that arrived by mail.",
    "generated": "A working session placed by rule. For each week, the threads the owner wrote on most "
                 "in the fortnight before get one session each, in a fixed weekly pattern. The owner is "
                 "the only attendee, and a session that overlaps an invitation is dropped.",
}


KINDS = ("meeting", "focus", "personal")


async def events_between(first: date, last: date | None = None) -> list[dict[str, Any]]:
    """Events from the calendar. A kind the policy does not know counts as a meeting."""
    result = await workspace.call("calendar_list_events", {
        "start_date": first.isoformat(), "end_date": (last or first).isoformat()})
    return [{**item, "kind": item.get("kind") if item.get("kind") in KINDS else "meeting"}
            for item in result.get("events", [])]


def _not_before(day: date) -> datetime | None:
    """Time that has passed today is not free."""
    return clock.now() if day == clock.today() else None


async def overview(day: date) -> dict[str, Any]:
    """One day: events, free slots, broken meeting rules and load."""
    persona = world.persona()
    events = policy.events_on(await events_between(day), day)
    return {"day": day.isoformat(), "weekday": day.strftime("%A"), "is_today": day == clock.today(),
            "events": events,
            "free_slots": policy.free_slots(events, day, persona, not_before=_not_before(day)),
            "meeting_rule_violations": policy.meeting_rule_violations(events, day, persona),
            "load": policy.day_load(events, day, persona),
            "rules": {"working_hours": f"{persona['work_start']} to {persona['work_end']}",
                      "no_meetings_before": persona["no_meetings_before"],
                      "minimum_slot_minutes": persona["pomodoro_minutes"],
                      "pomodoro_unit_minutes": persona["pomodoro_minutes"] + persona["break_minutes"],
                      "max_meeting_minutes_per_day": persona["max_meeting_minutes_per_day"]}}


async def week(first: date | None = None, days: int = 5) -> list[dict[str, Any]]:
    """Load for the next working days, each judged on its own."""
    first = first or clock.today()
    chosen = [first if first.weekday() < 5 else clock.business_day(first, 1)]
    while len(chosen) < days:
        chosen.append(clock.business_day(chosen[-1], 1))
    events = await events_between(chosen[0], chosen[-1])
    return [policy.day_load(events, item, world.persona()) for item in chosen]


async def plan(task_ids: list[str] | None = None, day: date | None = None, top: int = 3) -> dict[str, Any]:
    """Place tasks into the day's free slots, sized by estimated Pomodoros."""
    day = day or clock.today()
    persona = world.persona()
    if task_ids:
        chosen = [item for item in (tasks.get(task_id) for task_id in task_ids) if item]
        missing = [task_id for task_id in task_ids if tasks.get(task_id) is None]
    else:
        chosen, missing = tasks.governed()[:top], []
    chosen = [item for item in chosen if item["status"] == "OPEN"]
    summary = await overview(day)
    result = policy.plan_time_blocks(chosen, summary["free_slots"], persona)
    for item in chosen:
        if any(block["task_id"] == item["task_id"] for block in result["blocks"]):
            tasks.update(item["task_id"], planned_for=day.isoformat())
    markdown = plan_markdown(day, result)
    scratchfs.begin_session().write(scratchfs.PLAN_PATH, markdown, kind="plan",
                                    meta={"day": day.isoformat()})
    return {"day": day.isoformat(), "tasks": chosen, "unknown_task_ids": missing, **result,
            "free_slots": summary["free_slots"], "plan_path": scratchfs.PLAN_PATH,
            "rule": "A task stays whole when one slot can hold it; otherwise it is split one "
                    "Pomodoro at a time. No block overlaps an existing event."}


def plan_markdown(day: date, result: dict[str, Any]) -> str:
    lines = [f"# Plan for {day.strftime('%A %d %B')}", ""]
    if not result["blocks"]:
        lines.append("No blocks placed yet.")
    for block in result["blocks"]:
        lines.append(f"- {block['start_local']} to {block['end_local']}  {block['title']} "
                     f"({block['task_id']}, part {block['part']})")
    for item in result["unplaced"]:
        lines.append(f"- Not placed: {item['title']} ({item['task_id']}): {item['reason']}")
    return "\n".join(lines) + "\n"


def topic(event: dict[str, Any]) -> str:
    """What a meeting is about. A generated session is named after the thread it came from."""
    title = event["title"]
    return title[len(SESSION_PREFIX):] if title.startswith(SESSION_PREFIX) else title


def layers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The layers present among these events, with how many events each holds."""
    found = [item.get("source") for item in events]
    return [{"source": name, "about": about, "events": found.count(name)}
            for name, about in LAYERS.items() if name in found]


async def find_event(event_id: str) -> dict[str, Any] | None:
    first = clock.today() - timedelta(days=1)
    events = await events_between(first, first + timedelta(days=PREP_WINDOW_DAYS))
    return next((item for item in events if item["event_id"] == event_id), None)


async def upcoming_meetings(within_minutes: int) -> list[dict[str, Any]]:
    """Meetings that start soon: the condition behind the meeting-prep trigger."""
    now = clock.now()
    horizon = now + timedelta(minutes=within_minutes)
    events = await events_between(now.date(), horizon.date())
    return [item for item in events
            if item["kind"] == "meeting" and now < policy.parse_dt(item["start"]) <= horizon]


def _useful(event: dict[str, Any], threads: list[dict[str, Any]]) -> dict[str, Any]:
    """Which of the threads a search found are worth reading before this meeting.

    System One keeps at most three, and none when the search found noise. Without System One
    the first three keep the order of the search. The event's own thread is read separately."""
    from backend.core import system_one

    candidates = {item["thread_id"]: f"{item.get('subject', '')} | {item.get('from_email', '')} | "
                                     f"{item.get('snippet', '')}"
                  for item in threads if item["thread_id"] != event.get("related_thread")}
    return system_one.rerank(f"Prepare the owner for the meeting '{topic(event)}', organised by "
                             f"{event.get('organizer', '')}", candidates)


async def meeting_prep(event_id: str) -> dict[str, Any] | None:
    """Everything the harness holds about one meeting: thread, page, last notes and people."""
    event = await find_event(event_id)
    if event is None:
        return None
    from backend.core import inbox

    by_email = {item["email"]: item for item in store.contacts()}
    people = []
    for address in event.get("attendees", []):
        known = by_email.get(address.lower())
        if address.lower() != world.owner_email():
            people.append({"email": address, "name": known["name"] if known else None,
                           "role": known["role"] if known else None,
                           "is_vip": bool(known and known["is_vip"]), "known": known is not None})
    related_thread = related_page = None
    earlier: list[dict[str, Any]] = []
    try:
        if event.get("related_thread"):
            related_thread = await inbox.thread(event["related_thread"])
        # Mail on the same matter: the whole history, not just the inbox window. The event's own
        # thread stays in: for a generated session it is the evidence.
        matter = topic(event)
        for query in (matter, max(matter.split(), key=len, default="")):
            found = await workspace.call("mail_search_threads", {
                "query": query, "label": "ALL", "max_results": 10}) if query else {}
            earlier = found.get("threads", [])
            if earlier:
                break
        page_id = event.get("related_page")
        if not page_id:
            found = await workspace.call("notes_search", {"query": matter})
            page_id = found["pages"][0]["page_id"] if found.get("pages") else None
        if page_id:
            related_page = (await workspace.call("notes_get_page", {"page_id": page_id})).get("page")
    except WorkspaceError as exc:
        return {"event": event, "people": people, "error": str(exc)}
    ranking = await asyncio.to_thread(_useful, event, earlier)
    own = [item for item in earlier if item["thread_id"] == event.get("related_thread")]
    earlier = own + [item for name in ranking["kept"] for item in earlier if item["thread_id"] == name]
    actions = policy.extract_actions(related_page["body"], world.owner_first_name()) if related_page else []
    return {"event": event, "topic": topic(event), "people": people, "related_thread": related_thread,
            "related_page": related_page, "owner_actions": actions, "earlier_threads": earlier,
            "evidence_chosen_by": ranking["by"],
            "starts_in_minutes": round((policy.parse_dt(event["start"]) - clock.now()).total_seconds() / 60)}
