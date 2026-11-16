"""Approval gates and the action log.

Every effect the assistant causes leaves a row in ``ppa_action_audit``: what it
did, why, and what really happened. Gated actions move ``DRAFTED`` to
``APPROVED`` to ``EXECUTED``, or end ``REJECTED``. Approval and delivery are
recorded separately, because in safe mode an approved message may be held.
"""
from __future__ import annotations

from typing import Any

import policy

from backend.core import calendar_intel, clock, inbox, store, world
from backend.core.events import bus
from backend.core.workspace import WorkspaceError, workspace

TIERS = [
    {"tier": "automatic", "rule": "Runs without asking. Nobody else can see the result.",
     "examples": "every read; task add, update and complete; mail_create_draft; notes_create_page; "
                 "notes_append_to_page on a private page; focus timers; scratch and memory writes"},
    {"tier": "approval", "rule": "Pauses for a human decision. Another person will see the result.",
     "examples": "mail_send_message; calendar_create_event; calendar_respond_to_event; "
                 "notes_append_to_page on a shared page"},
    {"tier": "never exposed", "rule": "The server offers them. The allowlist does not.",
     "examples": "mail_trash_thread; calendar_delete_event; notes_share_page; notes_delete_page"},
]
# Measured by the course on its attack corpus; shown so nobody mistakes the tripwire for a defence.
TRIPWIRE_FINDING = {
    "measured_on": "microsoft/llmail-inject-challenge",
    "statement": "The pattern tripwire flags 31% of 3,000 real successful attacks and none of 203 "
                 "benign emails. Most attacks pass it, which is why the wrapper, the approval gate "
                 "and the recipient check do not depend on it.",
}


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    shaped = {**item, "payload": store.loads(item["payload"], {}), "risk": store.loads(item["risk"], {}),
              "result": store.loads(item["result"])}
    shaped["undoable"] = item["state"] == "EXECUTED" and item["tool_name"] in UNDOABLE \
        and not (shaped["result"] or {}).get("undone")
    return shaped


def summarise(tool_name: str, arguments: dict[str, Any]) -> str:
    """One readable line for the approval card and the action log."""
    get = arguments.get
    lines = {
        "mail_send_message": lambda: f"Send mail to {', '.join(get('to') or [])}: \"{get('subject', '')}\"",
        "mail_create_draft": lambda: f"Save a draft to {', '.join(get('to') or [])}: \"{get('subject', '')}\"",
        "calendar_create_event": lambda: f"Create event \"{get('title', '')}\" "
                                         f"{str(get('start', ''))[11:16]} to {str(get('end', ''))[11:16]} "
                                         f"on {str(get('start', ''))[:10]}",
        "calendar_respond_to_event": lambda: f"Answer invitation {get('event_id')}: {get('response')}",
        "notes_append_to_page": lambda: f"Append to page {get('page_id')}",
        "notes_create_page": lambda: f"Create private page \"{get('title', '')}\"",
        "task_add": lambda: f"Add task \"{get('title', '')}\"",
        "task_update": lambda: f"Update task {get('task_id')}",
        "task_complete": lambda: f"Complete task {get('task_id')}",
        "task_snooze": lambda: f"Snooze task {get('task_id')} until {get('until')}",
        "pomodoro_start": lambda: f"Start a {get('minutes') or 'default'}-minute focus session"
                                  + (f" on {get('task_id')}" if get("task_id") else ""),
        "pomodoro_stop": lambda: "Stop the focus session",
        "capture_note": lambda: f"Capture \"{str(get('text', ''))[:80]}\"",
        "scratch_write": lambda: f"Write {get('path')}",
        "memory_write": lambda: f"Remember ({get('memory_type')}): \"{str(get('content', ''))[:100]}\"",
        "plan_time_blocks": lambda: "Write the day plan",
        "end_workday": lambda: "End the workday session and promote marked notes",
    }
    return lines.get(tool_name, lambda: tool_name)()


def undo_hint(tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> str:
    """How to reverse the action, or a plain statement that it cannot be reversed."""
    reference = lambda key: result.get(key) or (result.get("task") or {}).get(key) or arguments.get(key)
    hints = {
        "mail_send_message": "Sent mail cannot be recalled. Send a correction if one is needed.",
        "mail_create_draft": f"Delete draft {reference('draft_id')} in the mail client. Nothing was sent.",
        "calendar_create_event": f"Delete event {reference('event_id')} in the calendar. "
                                 "The assistant cannot delete events.",
        "calendar_respond_to_event": "Change the response in the calendar. The organiser has been told.",
        "notes_append_to_page": f"Remove the appended text from page {reference('page_id')} in the notes app.",
        "notes_create_page": f"Delete page {reference('page_id')} in the notes app. "
                             "The assistant cannot delete pages.",
        "task_add": f"Undo drops task {reference('task_id')}.",
        "task_complete": f"Undo reopens task {reference('task_id')}.",
        "memory_write": f"Undo deletes memory {reference('memory_id')}.",
        "capture_note": f"Undo deletes {reference('path')} from the scratch inbox.",
        "pomodoro_start": "Stop the focus session to cancel its timer.",
        "end_workday": "The session can be resumed; promoted notes stay promoted.",
    }
    return hints.get(tool_name, "")


UNDOABLE = ("task_add", "task_complete", "memory_write", "capture_note")


def delivery_of(result: dict[str, Any]) -> str:
    """What actually happened, as opposed to what was approved."""
    if result.get("error"):
        return f"failed: {result.get('detail') or result['error']}"
    if result.get("status") == "held_by_safe_mode" or result.get("delivered") is False:
        return "held by safe mode: " + (result.get("detail") or "not delivered")
    if result.get("attendees_removed"):
        return "created without other attendees: " + (result.get("detail") or "safe mode is on")
    return str(result.get("delivery") or "delivered")


async def assess(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Why this action might deserve a second look."""
    flags: list[dict[str, Any]] = []
    level = "normal"
    owner = world.owner_email()
    try:
        if tool_name == "mail_send_message":
            recipients = [*(arguments.get("to") or []), *(arguments.get("cc") or [])]
            participants: list[str] = []
            if arguments.get("thread_id"):
                thread = await inbox.thread(arguments["thread_id"])
                if thread is None:
                    flags.append({"flag": "unknown_thread", "detail": "The thread ID does not exist."})
                else:
                    participants = thread["participants"]
                    if thread["category"] == "quarantine":
                        flags.append({"flag": "quarantined_thread",
                                      "detail": "This replies to a thread the tripwire quarantined."})
                        level = "high"
            risk = policy.recipient_risk(recipients, participants, store.contacts(), world.own_domain())
            for item in risk["flagged"]:
                flags.append({"flag": "recipient", "recipient": item["recipient"], "reasons": item["reasons"]})
            level = "high" if "high" in (level, risk["level"]) else risk["level"]
        elif tool_name == "calendar_create_event":
            persona = world.persona()
            start, end = clock.localise(arguments["start"]), clock.localise(arguments["end"])
            others = [item for item in arguments.get("attendees") or [] if item.lower() != owner]
            if others:
                flags.append({"flag": "invites_people", "detail": "Invitations go to " + ", ".join(others)})
            for event in await calendar_intel.events_between(start.date(), end.date()):
                if policy.parse_dt(event["start"]) < end and policy.parse_dt(event["end"]) > start:
                    flags.append({"flag": "conflict", "detail": f"Overlaps {event['title']} "
                                                               f"({event['event_id']})"})
            if start < clock.at(start.date(), persona["work_start"]) \
                    or end > clock.at(start.date(), persona["work_end"]):
                flags.append({"flag": "outside_working_hours",
                              "detail": f"Working hours are {persona['work_start']} to {persona['work_end']}."})
            if arguments.get("kind") == "meeting" and start < clock.at(start.date(), persona["no_meetings_before"]):
                flags.append({"flag": "meeting_rule",
                              "detail": f"No meetings before {persona['no_meetings_before']}."})
            level = "review" if flags else "normal"
        elif tool_name == "calendar_respond_to_event":
            event = await calendar_intel.find_event(arguments.get("event_id", ""))
            flags.append({"flag": "notifies_organiser", "detail": f"{event['organizer']} is told."}
                         if event else {"flag": "unknown_event", "detail": "The event ID does not exist."})
            level = "review"
        elif tool_name == "notes_append_to_page":
            flags.append({"flag": "shared_page", "detail": "Other people can see this page."})
            level = "review"
    except (WorkspaceError, KeyError, ValueError) as exc:
        flags.append({"flag": "not_assessed", "detail": str(exc)[:200]})
        level = "review"
    safe_mode = await workspace.safe_mode()
    return {"level": level, "flags": flags, "safe_mode": safe_mode,
            "safe_mode_effect": safe_mode_effect(tool_name, arguments, safe_mode)}


def safe_mode_effect(tool_name: str, arguments: dict[str, Any], safe_mode: bool) -> str | None:
    """What safe mode will do to this action if it is approved."""
    if workspace.practising():
        return "Practice workspace: nothing leaves this machine."
    if not safe_mode:
        return "Safe mode is off: approval delivers this for real."
    owner = world.owner_email()
    if tool_name == "mail_send_message":
        others = [item for item in [*(arguments.get("to") or []), *(arguments.get("cc") or [])]
                  if item.lower() != owner]
        return "Safe mode is on: the message will be held as a draft." if others else None
    if tool_name == "calendar_create_event":
        others = [item for item in arguments.get("attendees") or [] if item.lower() != owner]
        return "Safe mode is on: the event will be created without other attendees." if others else None
    return "Safe mode is on: nobody else will be notified."


def draft(tool_name: str, arguments: dict[str, Any], *, reason: str, risk: dict[str, Any],
          thread_id: str, session_id: str, run_id: str | None, origin: str) -> dict[str, Any]:
    """Record a gated action that is waiting for a human decision."""
    action_id = store.new_id("ACT")
    store.execute(
        "INSERT INTO ppa_action_audit(action_id,run_id,thread_id,session_id,origin,tool_name,tier,summary,"
        "reason,payload,risk,state,created_at,real_created_at) VALUES (?,?,?,?,?,?,'approval',?,?,?,?,'DRAFTED',?,?)",
        (action_id, run_id, thread_id, session_id, origin, tool_name, summarise(tool_name, arguments),
         reason, store.dumps(arguments), store.dumps(risk), clock.stamp(), store.real_now()))
    return _announce(action_id)


def record(tool_name: str, arguments: dict[str, Any], result: dict[str, Any], *, reason: str,
           thread_id: str, session_id: str, run_id: str | None, origin: str) -> dict[str, Any]:
    """Record an automatic effect. It ran without asking because nobody else can see it."""
    action_id = store.new_id("ACT")
    failed = bool(result.get("error"))
    stamp = clock.stamp()
    store.execute(
        "INSERT INTO ppa_action_audit(action_id,run_id,thread_id,session_id,origin,tool_name,tier,summary,"
        "reason,payload,state,delivery,result,undo_hint,created_at,executed_at,real_created_at) "
        "VALUES (?,?,?,?,?,?,'automatic',?,?,?,?,?,?,?,?,?,?)",
        (action_id, run_id, thread_id, session_id, origin, tool_name, summarise(tool_name, arguments),
         reason, store.dumps(arguments), "FAILED" if failed else "EXECUTED",
         delivery_of(result) if failed else "internal: nobody else can see it", store.dumps(result),
         "" if failed else undo_hint(tool_name, arguments, result), stamp, stamp, store.real_now()))
    return _announce(action_id)


def decide(action_id: str, decision: str, note: str = "") -> dict[str, Any]:
    """The human decision. Only a drafted action can be decided, and only once."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    state = "APPROVED" if decision == "approve" else "REJECTED"
    changed = store.execute(
        "UPDATE ppa_action_audit SET state=?,decided_at=?,decision_note=?,delivery=? "
        "WHERE action_id=? AND state='DRAFTED'",
        (state, clock.stamp(), note, None if decision == "approve" else "not executed: declined",
         action_id))
    if not changed and get(action_id) is None:
        raise KeyError(action_id)
    return _announce(action_id)


def executed(action_id: str, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Record what the gateway reports really happened."""
    failed = bool(result.get("error"))
    store.execute(
        "UPDATE ppa_action_audit SET state=?,executed_at=?,result=?,delivery=?,undo_hint=? "
        "WHERE action_id=? AND state='APPROVED'",
        ("FAILED" if failed else "EXECUTED", clock.stamp(), store.dumps(result), delivery_of(result),
         "" if failed else undo_hint(tool_name, arguments, result), action_id))
    return _announce(action_id)


def mark_undone(action_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
    current = get(action_id)
    result = {**(current["result"] or {}), "undone": outcome}
    store.execute("UPDATE ppa_action_audit SET result=?,delivery=? WHERE action_id=?",
                  (store.dumps(result), "undone by the user", action_id))
    return _announce(action_id)


def _announce(action_id: str) -> dict[str, Any]:
    shaped = get(action_id)
    bus.publish("action", **shaped)
    return shaped


def get(action_id: str) -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_action_audit WHERE action_id=?", (action_id,))
    return _shape(found) if found else None


def pending(thread_id: str | None = None) -> list[dict[str, Any]]:
    found = store.rows("SELECT * FROM ppa_action_audit WHERE state='DRAFTED' ORDER BY rowid")
    return [_shape(item) for item in found if thread_id is None or item["thread_id"] == thread_id]


def log(limit: int = 60) -> list[dict[str, Any]]:
    return [_shape(item) for item in store.rows(
        "SELECT * FROM ppa_action_audit ORDER BY rowid DESC LIMIT ?", (limit,))]
