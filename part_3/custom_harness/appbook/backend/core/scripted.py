"""The scripted responder: a deterministic stand-in for the model.

With no API key the appbook still runs the whole loop. This responder sits
where the model sits: it receives the conversation, returns tool calls, reads
the tool results and writes the answer. It routes a fixed set of intents to the
same trusted tools and knows nothing about the data in advance; every name and
ID it prints comes from a tool result.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.core import clock, inbox, skills, world
from backend.core.memory import keywords

LABEL = "scripted responder"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
INTENTS: list[tuple[str, str]] = [
    ("pomodoro_stop", r"\b(stop|end|cancel)\b.*\b(pomodoro|focus|timer|session)\b"),
    ("pomodoro_status", r"\b(how long|time left|status)\b.*\b(pomodoro|focus|timer|session|left)\b"),
    ("pomodoro_start", r"\b(pomodoro|focus session|focus on|start a timer)\b"),
    ("morning_brief", r"\b(morning brief|brief me|start my day)\b"),
    ("triage", r"\btriage\b|\binbox\b.*\b(task|actionable|sort)"),
    ("time_block", r"time[- ]?block|\bblock\b.*\btasks?\b|schedule my top"),
    ("weekly_review", r"weekly review|review (of )?my week|week in review"),
    ("end_of_day", r"end[- ]of[- ]day|wrap up|wrap my day|close (out )?my day"),
    ("meeting_prep", r"\bprep(are)?\b.*\b(meeting|call|event)\b|\bmeeting prep\b|prepare me for"),
    ("send_reply", r"\bsend\b.*\b(reply|email|e-mail|message|mail)\b|\breply to\b.*\bsend\b"),
    ("recall", r"what should i know|before i plan|what do you (know|remember)|do you remember"),
    ("remember", r"\bfrom now on\b|\bremember (that|this)\b|\bremember:|\bi prefer\b|\bin future\b"),
    ("task_add", r"^(add|create) (a )?task\b|\bnew task\b"),
    ("task_done", r"\b(mark|complete|finish(ed)?|done)\b.*\btask\b|\btask\b.*\b(done|complete)\b"),
    ("task_list", r"\b(my|list|show|open)\b.*\btasks\b|what.*on my list"),
    ("week_load", r"over-?booked|busy.*week|week.*(look|load)"),
    ("agenda", r"\b(calendar|agenda|schedule|meetings?)\b.*\b(today|tomorrow|" + "|".join(WEEKDAYS) + r")\b"
               r"|what.*\b(on|free)\b.*\b(today|tomorrow)\b|\bam i free\b"),
    ("capture", r"^(note|capture|jot|remind me)\b"),
]
TRIGGER_INTENTS = {"morning_brief": "morning_brief", "end_of_day_wrap": "end_of_day",
                   "weekly_review": "weekly_review", "meeting_prep": "meeting_prep",
                   "vip_alert": "vip_alert", "pomodoro": "focus_end"}
ID_PATTERN = re.compile(r"`([^`\s]+)`|\b((?:thr|EV|FS|T|page)-[A-Za-z0-9]+)\b")


def _ids(text: str) -> list[str]:
    """IDs named in a request: anything in backticks, or a token shaped like a harness ID."""
    return [quoted or bare for quoted, bare in ID_PATTERN.findall(text)]


# ── Reading the conversation ─────────────────────────────────────────────────

def _turn(messages: list[Any]) -> tuple[HumanMessage, list[dict[str, Any]]]:
    """The current request and every tool result gathered for it so far."""
    start = max(index for index, item in enumerate(messages) if isinstance(item, HumanMessage))
    calls: dict[str, dict[str, Any]] = {}
    results = []
    for item in messages[start + 1:]:
        if isinstance(item, AIMessage):
            calls.update({call["id"]: call for call in item.tool_calls})
        elif isinstance(item, ToolMessage) and item.tool_call_id in calls:
            call = calls[item.tool_call_id]
            try:
                payload = json.loads(item.content if isinstance(item.content, str) else item.content[0]["text"])
            except (ValueError, KeyError, IndexError, TypeError):
                payload = {"text": str(item.content)}
            results.append({"id": call["id"], "name": call["name"], "args": call["args"], "result": payload})
    return messages[start], results


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [part.strip() for part in parts if part.strip()]


def detect(request: str, trigger: str) -> list[tuple[str, str]]:
    """The intents in a request, in order. A proactive trigger names its own."""
    if trigger in TRIGGER_INTENTS:
        return [(TRIGGER_INTENTS[trigger], request)]
    found: list[tuple[str, str]] = []
    for sentence in _sentences(request):
        lowered = sentence.lower()
        match = next((name for name, pattern in INTENTS if re.search(pattern, lowered)), None)
        if match and match not in [name for name, _ in found]:
            found.append((match, sentence))
    return found or [("help", request)]


class Slot:
    """One intent's view of the turn: its own results and a way to ask for more."""

    def __init__(self, index: int, text: str, results: list[dict[str, Any]]) -> None:
        self.index, self.text = index, text
        self.results = [item for item in results if item["id"].startswith(f"s{index}_")]

    def got(self, name: str) -> dict[str, Any] | None:
        return next((item["result"] for item in self.results if item["name"] == name), None)

    def every(self, name: str) -> list[dict[str, Any]]:
        return [item for item in self.results if item["name"] == name]

    def call(self, tool: str, /, **arguments: Any) -> dict[str, Any]:
        number = sum(1 for item in self.pending if item["name"] == tool) + len(self.every(tool)) + 1
        entry = {"type": "tool_call", "name": tool, "args": arguments,
                 "id": f"s{self.index}_{tool}_{number}"}
        self.pending.append(entry)
        return entry

    pending: list[dict[str, Any]]


# ── Small renderers ──────────────────────────────────────────────────────────

def _time(value: str | None) -> str:
    return clock.localise(value).strftime("%H:%M") if value else ""


def _day(value: str) -> str:
    return clock.localise(value).strftime("%A %d %B")


def _outcome(result: dict[str, Any]) -> str:
    if result.get("status") == "declined_by_user":
        return "declined by you, so nothing was written"
    if result.get("status") == "held_by_safe_mode" or result.get("delivered") is False:
        return "approved, but held by safe mode and not delivered"
    if result.get("error"):
        return f"failed ({result.get('detail') or result['error']})"
    if result.get("attendees_removed"):
        return "created without other attendees, because safe mode is on"
    return str(result.get("status") or "done")


def _task_line(item: dict[str, Any]) -> str:
    due = f", due {_day(item['due_at'])} {_time(item['due_at'])}" if item.get("due_at") else ""
    flags = "".join([" · urgent" if item.get("urgent") else "",
                     f" · carried over {item['carry_over_count']}x" if item.get("carry_over_count") else ""])
    return (f"**{item['title']}** (`{item['task_id']}`, priority {item['priority']}, "
            f"{item['est_pomodoros']} Pomodoro{'s' if item['est_pomodoros'] != 1 else ''}{due}){flags}")


def _event_line(item: dict[str, Any], broken: set[str]) -> str:
    rule = world.persona()["no_meetings_before"]
    note = f" - breaks the no-meetings-before-{rule} rule" if item["event_id"] in broken else ""
    return (f"{_time(item['start'])} to {_time(item['end'])} **{item['title']}** "
            f"(`{item['event_id']}`, {item['kind']}){note}")


def _slots(slots: list[dict[str, Any]]) -> str:
    return ", ".join(f"{item['start_local']} to {item['end_local']}" for item in slots) or "none"


def _quarantined(rows: list[dict[str, Any]]) -> list[str]:
    return [f"`{row['thread_id']}` from {row['from_email']} ({', '.join(row['injection_patterns'])})"
            for row in rows if row["category"] == "quarantine"]


def _target_day(text: str) -> str | None:
    """The day a request is about, when it names one."""
    lowered, today = text.lower(), clock.today()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()
    for index, name in enumerate(WEEKDAYS):
        if name in lowered:
            return (today + timedelta(days=(index - today.weekday()) % 7)).isoformat()
    return today.isoformat() if "today" in lowered else None


# ── Intent scripts: each returns the answer, or None while it waits on tools ──

def morning_brief(slot: Slot) -> str | None:
    if slot.got("triage_inbox") is None:
        slot.call("load_skill", name="morning-brief")
        slot.call("triage_inbox")
        slot.call("day_overview")
        slot.call("task_list", status="OPEN")
        return None
    triage, day, listed = slot.got("triage_inbox"), slot.got("day_overview"), slot.got("task_list")
    rows = [row for row in triage.get("rows", []) if row["category"] in inbox.ACTIONABLE]
    lines = [f"## Morning brief · {_day(clock.stamp())}", "", "### Needs you first"]
    if rows:
        first = rows[0]
        lines.append(f"- **{first['from_name']}**: {first['subject']} (`{first['thread_id']}`). "
                     f"{first['reason'].capitalize()}"
                     + ("; the sender is a VIP." if first["vip"] else "."))
        lines += [f"- {row['from_name']}: {row['subject']} (`{row['thread_id']}`)" for row in rows[1:3]]
    else:
        lines.append("- Nothing in the inbox needs an answer.")
    broken = {item["event_id"] for item in day.get("meeting_rule_violations", [])}
    lines += ["", "### Today"]
    lines += [f"- {_event_line(item, broken)}" for item in day.get("events", [])] or ["- No events."]
    if broken:
        lines.append("- I can propose a later time for the early meeting; answering an invitation "
                     "needs your approval.")
    lines += ["", "### Top tasks"]
    top = listed.get("tasks", [])[:3]
    lines += [f"{index}. {_task_line(item)}" for index, item in enumerate(top, 1)] or \
        ["- No tasks yet. Ask me to triage the inbox and I will extract them."]
    lines += ["", "### Free for focus", f"- {_slots(day.get('free_slots', []))}"]
    held = _quarantined(triage.get("rows", []))
    if held:
        lines += ["", "### Held back", *[f"- Quarantined, not opened: {item}" for item in held]]
    return "\n".join(lines)


def triage(slot: Slot) -> str | None:
    found = slot.got("triage_inbox")
    if found is None:
        slot.call("load_skill", name="inbox-triage")
        slot.call("triage_inbox")
        return None
    rows = found.get("rows", [])
    actionable = [row for row in rows if row["category"] in inbox.ACTIONABLE and row.get("suggested_task")]
    if actionable and not slot.every("task_add"):
        for row in actionable:
            slot.call("task_add", **row["suggested_task"], reason=f"Triage: {row['reason']}.")
            draft = inbox.draft_for(row)
            if draft:
                slot.call("mail_create_draft", **draft,
                          reason="Holding reply saved as a draft; nothing is sent without approval.")
        return None
    by_thread = {row["thread_id"]: row for row in rows}
    created, suppressed = [], []
    for item in slot.every("task_add"):
        result, thread = item["result"], item["args"].get("source_ref")
        line = (f"`{result.get('task_id')}` {item['args']['title']} "
                f"(from `{thread}`, {by_thread[thread]['category']})")
        (created if result.get("status") == "created" else suppressed).append(line)
    drafts = [f"`{item['result'].get('draft_id')}` to {', '.join(item['args']['to'])} "
              f"(thread `{item['args']['thread_id']}`)" for item in slot.every("mail_create_draft")
              if not item["result"].get("error")]
    tracked = [f"`{row['thread_id']}` is covered by `{row['tracked_task_id']}`"
               for row in rows if row["category"] == "tracked"]
    counts = found.get("counts", {})
    lines = [f"## Inbox triage · {len(rows)} threads",
             "", " · ".join(f"{name} {total}" for name, total in counts.items() if total)]
    lines += ["", f"### New tasks ({len(created)})", *[f"- {item}" for item in created]]
    if suppressed:
        lines += ["", "### No duplicate created", *[f"- {item}" for item in suppressed]]
    if tracked:
        lines += ["", "### Already tracked", *[f"- {item}" for item in tracked]]
    if drafts:
        lines += ["", f"### Drafts saved, not sent ({len(drafts)})", *[f"- {item}" for item in drafts]]
    held = _quarantined(rows)
    if held:
        lines += ["", "### Quarantined", *[f"- {item}. Not opened, answered or forwarded." for item in held]]
    unknown = found.get("unknown_senders", {})
    if unknown.get("threads"):
        lines += ["", f"{unknown['threads']} threads came from senders you have never written to; the "
                      f"tripwire flagged {unknown['flagged_by_tripwire']}. Treat the rest with care: "
                      "their text reaches me as data, and anything outward still needs your approval."]
    return "\n".join(lines)


def time_block(slot: Slot) -> str | None:
    listed = slot.got("task_list")
    if listed is None:
        slot.call("load_skill", name="time-block-tasks")
        slot.call("task_list", status="OPEN")
        return None
    top = listed.get("tasks", [])[:3]
    if not top:
        return "## Time blocks\n\nThere are no open tasks to place. Ask me to triage the inbox first."
    plan = slot.got("plan_time_blocks")
    if plan is None:
        slot.call("plan_time_blocks", task_ids=[item["task_id"] for item in top], date=_target_day(slot.text),
                  reason="Place the top three tasks into free slots.")
        return None
    if plan.get("blocks") and not slot.every("calendar_create_event"):
        for block in plan["blocks"]:
            slot.call("calendar_create_event", title=f"Focus: {block['title']}", start=block["start"],
                      end=block["end"], kind="focus", attendees=[],
                      description=f"Time block for {block['task_id']}, part {block['part']}.",
                      reason=f"Protect {block['pomodoros']} Pomodoro(s) for {block['task_id']}.")
        return None
    lines = [f"## Time blocks · {_day(plan['day'])}", ""]
    for block, item in zip(plan.get("blocks", []), slot.every("calendar_create_event"), strict=False):
        event = item["result"].get("event_id")
        lines.append(f"- {block['start_local']} to {block['end_local']} **{block['title']}** "
                     f"(`{block['task_id']}`, part {block['part']}): {_outcome(item['result'])}"
                     + (f", event `{event}`" if event else ""))
    lines += [f"- Not placed: {item['title']} (`{item['task_id']}`): {item['reason']}"
              for item in plan.get("unplaced", [])]
    if any(item["result"].get("status") == "declined_by_user" for item in slot.every("calendar_create_event")):
        lines += ["", "Declined blocks were not written and I will not retry them. "
                      f"The plan is still in `{plan['plan_path']}`."]
    return "\n".join(lines)


def _match_task(hint: str, listed: dict[str, Any]) -> dict[str, Any] | None:
    wanted = keywords(re.sub(r"\b(start|a|pomodoro|focus|session|on|the|for|timer|task)\b", " ", hint.lower()))
    scored = [(len(wanted & keywords(item["title"])), -index, item)
              for index, item in enumerate(listed.get("tasks", []))]
    scored = [entry for entry in scored if entry[0]]
    return max(scored)[2] if scored else None


def pomodoro_start(slot: Slot) -> str | None:
    listed = slot.got("task_list")
    if listed is None:
        slot.call("load_skill", name="focus-session")
        slot.call("task_list", status="OPEN")
        return None
    started = slot.got("pomodoro_start")
    if started is None:
        added = slot.got("task_add")
        task = _match_task(slot.text, listed)
        hint = re.sub(r"^.*?\b(?:on|for)\s+", "", slot.text.rstrip(".!?"), count=1, flags=re.IGNORECASE)
        minutes = re.search(r"(\d+)[- ]?min", slot.text.lower())
        if task is None and added is None and hint and hint != slot.text.rstrip(".!?"):
            slot.call("task_add", title=hint[0].upper() + hint[1:], source_type="chat",
                      reason="No open task matched the focus request, so one was created.")
            return None
        slot.call("pomodoro_start", task_id=(task or {}).get("task_id") or (added or {}).get("task_id"),
                  minutes=int(minutes.group(1)) if minutes else None,
                  reason="Asked to start a focus session.")
        return None
    if started.get("status") == "already_running":
        session = started["session"]
        return (f"A focus session is already running (`{session['session_id']}`), with "
                f"{session['seconds_remaining'] // 60} minutes left. Stop it before starting another.")
    if started.get("error"):
        return f"I could not start the focus session: {started.get('detail') or started['error']}."
    session = started["session"]
    subject = f"**{session['task_title']}** (`{session['task_id']}`)" if session.get("task_id") \
        else "unplanned focus"
    return (f"Focus session `{session['session_id']}` started on {subject}: {started['minutes']} minutes. "
            f"Timer `{started['job']['job_id']}` is armed and survives a restart. "
            "Tell me anything that distracts you and I will park it until the break.")


def pomodoro_stop(slot: Slot) -> str | None:
    stopped = slot.got("pomodoro_stop")
    if stopped is None:
        slot.call("pomodoro_stop", reason="Asked to stop the focus session.")
        return None
    if stopped.get("status") != "stopped":
        return "No focus session is running."
    session = stopped["session"]
    parked = stopped.get("distractions", [])
    return (f"Stopped `{session['session_id']}` after {session['actual_minutes']} of "
            f"{session['planned_minutes']} minutes."
            + (" Parked during the session: " + "; ".join(parked) + "." if parked else ""))


def pomodoro_status(slot: Slot) -> str | None:
    found = slot.got("pomodoro_status")
    if found is None:
        slot.call("pomodoro_status")
        return None
    if found.get("status") != "running":
        return "No focus session is running."
    session = found["session"]
    return (f"`{session['session_id']}` is running on "
            f"{session.get('task_title') or 'unplanned focus'}: "
            f"{session['seconds_remaining'] // 60} min {session['seconds_remaining'] % 60} s left.")


def focus_end(slot: Slot) -> str | None:
    found = slot.got("focus_session_report")
    if found is None:
        slot.call("focus_session_report", session_id=next(iter(_ids(slot.text)), ""))
        return None
    if found.get("error"):
        return "Session finished."
    session, parked = found["session"], found.get("distractions", [])
    lines = [f"Session finished: {session['actual_minutes']} minutes on "
             f"{session.get('task_title') or 'unplanned focus'}."]
    if parked:
        lines.append("Parked while you worked: " + "; ".join(parked) + ".")
    lines.append(f"Take a {found['break_minutes']}-minute break.")
    return " ".join(lines)


def remember(slot: Slot) -> str | None:
    written = slot.got("memory_write")
    if written is None:
        content = re.sub(r"^(also|and|please|oh)[, ]+", "", slot.text.strip(), flags=re.IGNORECASE)
        content = re.sub(r"^(from now on|in future|remember (that|this)|remember:?)[, ]*", "", content,
                         flags=re.IGNORECASE).strip().rstrip(".!") + "."
        kind = "fact" if re.search(r"\bremember (that|this)\b", slot.text.lower()) else "preference"
        slot.call("memory_write", memory_type=kind, content=content[0].upper() + content[1:],
                  reason="Stated by the owner as a standing instruction.")
        return None
    memory = written.get("memory", {})
    verb = "I already had this" if written.get("status") == "already_known" else "Saved to long-term memory"
    return f"{verb} as a {memory.get('memory_type')}: \"{memory.get('content')}\" (`{written.get('memory_id')}`)."


def recall(slot: Slot) -> str | None:
    found = slot.got("memory_search")
    if found is None:
        slot.call("memory_search", query=slot.text, limit=8)
        slot.call("day_overview", date=_target_day(slot.text))
        slot.call("task_list", status="OPEN")
        return None
    day, listed = slot.got("day_overview") or {}, slot.got("task_list") or {}
    matched = found.get("memories", [])
    shown = {item["memory_id"] for item in matched}
    standing = [item for item in found.get("standing", []) if item["memory_id"] not in shown]
    lines = [f"## Before you plan {day.get('weekday', 'the day')}", "", "### From long-term memory"]
    lines += [f"- {item['content']} ({item['memory_type']}, `{item['memory_id']}`)"
              for item in [*matched, *standing]] or ["- Nothing is stored yet."]
    lines += ["", f"### {day.get('weekday', 'That day')} on the calendar"]
    broken = {item["event_id"] for item in day.get("meeting_rule_violations", [])}
    lines += [f"- {_event_line(item, broken)}" for item in day.get("events", [])] or ["- No events."]
    lines.append(f"- Free: {_slots(day.get('free_slots', []))}")
    due = [item for item in listed.get("tasks", [])
           if item.get("due_at") and item["due_at"][:10] <= day.get("day", "")]
    if due:
        lines += ["", "### Due by then", *[f"- {_task_line(item)}" for item in due]]
    return "\n".join(lines)


def weekly_review(slot: Slot) -> str | None:
    data = slot.got("weekly_review_data")
    if data is None:
        slot.call("load_skill", name="weekly-review")
        slot.call("weekly_review_data")
        return None
    period = data["period"]
    lines = [f"## Weekly review · {_day(period['from'])} to {_day(period['to'])}", ""]
    if data.get("empty"):
        return "\n".join(lines + ["Nothing has been planned, worked on or completed in this period yet. "
                                  "Triage the inbox, block some time and run a focus session; the "
                                  "review fills in from what actually happens."])
    done, focus = data["planned_vs_done"], data["focus"]
    lines += ["### Planned versus done",
              f"- {done['done']} of {done['planned']} planned tasks done ({done['percent']}%).",
              f"- Focus: {focus['actual_minutes']} of {focus['planned_minutes']} planned minutes "
              f"({focus['completion_percent']}%), {focus['interrupted']} of {focus['sessions']} "
              "sessions interrupted.", "", "### Where time went"]
    lines += [f"- {item['minutes']} min · {item['title']}" for item in data["time_by_task"]] or \
        ["- No focus sessions recorded."]
    lines += ["", "### What keeps slipping"]
    lines += [f"- **{item['title']}** (`{item['task_id']}`), carried over {item['carry_over_count']} times"
              for item in data["slipping"]] or ["- Nothing has slipped twice."]
    lines += ["", "### What to drop"]
    lines += [f"- **{item['title']}** (`{item['task_id']}`), untouched since {_day(item['touched_at'])}"
              for item in data["drop_candidates"]] or ["- No stale tasks."]
    return "\n".join(lines)


def end_of_day(slot: Slot) -> str | None:
    data = slot.got("end_of_day_data")
    if data is None:
        slot.call("load_skill", name="end-of-day-wrap")
        slot.call("end_of_day_data")
        return None
    ended = slot.got("end_workday")
    if ended is None:
        slot.call("end_workday", reason="End-of-day wrap: close the workday session.")
        return None
    tomorrow = data["tomorrow"]
    lines = [f"## End of day · {data['weekday']}", "", "### Done"]
    lines += [f"- {item['title']} (`{item['task_id']}`)" for item in data["done"]] or ["- Nothing completed today."]
    lines += ["", "### Carried over"]
    lines += [f"- {item['title']} (`{item['task_id']}`), now carried over {item['carry_over_count']} times"
              for item in ended.get("carried_over", [])] or ["- Nothing planned was left open."]
    slot_text = "no free slot" if not tomorrow["first_free_slot"] else \
        f"{tomorrow['first_free_slot']['start_local']} to {tomorrow['first_free_slot']['end_local']}"
    first = tomorrow["first_task"]
    lines += ["", f"### {tomorrow['weekday']}'s first block",
              f"- {slot_text}" + (f": **{first['title']}** (`{first['task_id']}`)" if first else "")]
    lines += ["", f"Session `{ended['session_id']}` ended. {ended['promoted']} note(s) promoted, "
                  f"{ended['duplicates']} duplicate(s) skipped."]
    return "\n".join(lines)


def meeting_prep(slot: Slot) -> str | None:
    day = slot.got("day_overview")
    if day is None:
        slot.call("load_skill", name="meeting-prep")
        slot.call("day_overview", date=_target_day(slot.text))
        return None
    prep = slot.got("meeting_prep")
    if prep is None:
        events = day.get("events", [])
        named = set(_ids(slot.text))
        wanted = keywords(slot.text)
        chosen = next((item for item in events if item["event_id"] in named), None) \
            or max(events, key=lambda item: len(wanted & keywords(item["title"])), default=None)
        if chosen is None and not named:
            return "There is no meeting on the calendar for that day to prepare."
        slot.call("meeting_prep", event_id=chosen["event_id"] if chosen else sorted(named)[0])
        return None
    if prep.get("error") and not prep.get("event"):
        return f"I could not find that event: {prep.get('detail') or prep['error']}."
    event = prep["event"]
    lines = [f"## Meeting prep · {event['title']}",
             f"{_day(event['start'])}, {_time(event['start'])} to {_time(event['end'])} "
             f"(`{event['event_id']}`), your response: {event.get('response', 'unknown')}.", "", "### People"]
    lines += [f"- {item.get('name') or item['email']}"
              + (" · VIP" if item["is_vip"] else "") + ("" if item["known"] else " · not a known contact")
              for item in prep.get("people", [])] or ["- Only you."]
    thread = prep.get("related_thread")
    if thread:
        heading = "The thread this session is about" if event.get("source") == "generated" \
            else "The invitation"
        lines += ["", f"### {heading}", f"- `{thread['thread_id']}` from {thread['from_name']}: "
                                        f"{thread['subject']} ({thread['reason']})"]
    earlier = prep.get("earlier_threads", [])
    if earlier:
        lines += ["", f"### Mail on this matter ({len(earlier)})"]
        lines += [f"- `{item['thread_id']}` {item['received_at'][:10]} {item['from_email']}: {item['subject']}"
                  for item in earlier[:5]]
    page = prep.get("related_page")
    if page:
        lines += ["", "### Notes", f"- `{page['page_id']}` {page['title']}"]
    lines += [f"- Your open action: {item}" for item in prep.get("owner_actions", [])]
    if event["event_id"] in {item["event_id"] for item in day.get("meeting_rule_violations", [])}:
        lines += ["", f"This meeting starts before {world.persona()['no_meetings_before']}, your earliest "
                      "meeting time."]
    return "\n".join(lines)


def vip_alert(slot: Slot) -> str | None:
    found = slot.got("mail_get_thread")
    if found is None:
        slot.call("mail_get_thread", thread_id=next(iter(_ids(slot.text)), ""))
        return None
    if found.get("error"):
        return "A message arrived from a VIP sender, but I could not read the thread."
    return f"New mail from {found['from_name']} (VIP): {found['subject']} (`{found['thread_id']}`)."


def send_reply(slot: Slot) -> str | None:
    found = slot.got("triage_inbox")
    if found is None:
        slot.call("triage_inbox")
        return None
    sent = slot.got("mail_send_message")
    if sent is None:
        wanted = keywords(slot.text)
        named = set(_ids(slot.text))
        rows = [row for row in found.get("rows", []) if row["category"] != "quarantine"]
        scored = [(row["thread_id"] in named, len(wanted & keywords(f"{row['from_name']} {row['subject']}")),
                   -index, row) for index, row in enumerate(rows)]
        scored = [entry for entry in scored if entry[0] or entry[1]]
        if not scored:
            return "I could not tell which thread you mean. Name the sender or the subject."
        row = max(scored)[3]
        draft = inbox.draft_for({**row, "category": "reply", "labels": []})
        slot.call("mail_send_message", **draft, cc=[],
                  reason=f"Asked to send a reply on thread {row['thread_id']}.")
        return None
    call = slot.every("mail_send_message")[0]["args"]
    return (f"Reply to {', '.join(call['to'])} on `{call['thread_id']}`: {_outcome(sent)}."
            + (" I will not retry it." if sent.get("status") == "declined_by_user" else ""))


def task_add(slot: Slot) -> str | None:
    added = slot.got("task_add")
    if added is None:
        title = re.sub(r"^(add|create) (a )?(new )?task:?\s*", "", slot.text.rstrip(".!"), flags=re.IGNORECASE)
        slot.call("task_add", title=title[0].upper() + title[1:] if title else "Untitled task",
                  source_type="chat", reason="Asked to add a task.")
        return None
    if added.get("status") == "already_tracked":
        return f"That is already tracked as `{added['task_id']}`. No duplicate was created."
    return f"Added {_task_line(added['task'])}."


def task_done(slot: Slot) -> str | None:
    listed = slot.got("task_list")
    if listed is None:
        slot.call("task_list", status="OPEN")
        return None
    done = slot.got("task_complete")
    if done is None:
        named = set(_ids(slot.text))
        task = next((item for item in listed.get("tasks", []) if item["task_id"] in named), None) \
            or _match_task(re.sub(r"\b(mark|complete|finished?|done|as)\b", " ", slot.text.lower()), listed)
        if task is None:
            return "I could not tell which task you mean."
        slot.call("task_complete", task_id=task["task_id"], reason="The owner said it is done.")
        return None
    return f"Completed **{done['task']['title']}** (`{done['task_id']}`)."


def task_list(slot: Slot) -> str | None:
    listed = slot.got("task_list")
    if listed is None:
        slot.call("task_list", status="OPEN")
        return None
    lines = [f"## Open tasks ({listed['count']})", ""]
    lines += [f"{index}. {_task_line(item)}" for index, item in enumerate(listed["tasks"], 1)] or \
        ["No open tasks yet."]
    return "\n".join(lines)


def agenda(slot: Slot) -> str | None:
    day = slot.got("day_overview")
    if day is None:
        slot.call("day_overview", date=_target_day(slot.text))
        return None
    broken = {item["event_id"] for item in day.get("meeting_rule_violations", [])}
    lines = [f"## {day['weekday']} {day['day']}", ""]
    lines += [f"- {_event_line(item, broken)}" for item in day.get("events", [])] or ["- No events."]
    lines += ["", f"Free: {_slots(day.get('free_slots', []))}.",
              f"Meetings: {day['load']['meeting_minutes']} minutes"
              + (" - over-booked." if day["load"]["overbooked"] else ".")]
    return "\n".join(lines)


def week_load(slot: Slot) -> str | None:
    found = slot.got("week_load")
    if found is None:
        slot.call("week_load")
        return None
    limit = world.persona()["max_meeting_minutes_per_day"]
    lines = ["## The coming working days", ""]
    lines += [f"- {item['weekday']} {item['day']}: {item['meeting_minutes']} meeting minutes, "
              f"{item['free_minutes']} free" + (" - **over-booked**" if item["overbooked"] else "")
              for item in found["days"]]
    lines += ["", f"A day is over-booked above {limit} meeting minutes. "
                  + (f"{len(found['overbooked_days'])} day(s) are." if found["overbooked_days"]
                     else "None are.")]
    return "\n".join(lines)


def capture(slot: Slot) -> str | None:
    captured = slot.got("capture_note")
    if captured is None:
        text = re.sub(r"^(note|capture|jot( down)?)[:,]?\s*", "", slot.text, flags=re.IGNORECASE)
        slot.call("capture_note", text=text)
        return None
    parked = " as a distraction from the running focus session" if captured.get("kind") == "distraction" else ""
    return f"Captured in `{captured['path']}`{parked}. It becomes a task when the workday ends."


def help_(slot: Slot) -> str | None:
    return ("I am running as the scripted responder, so I follow a fixed set of requests: "
            "prepare my morning brief; triage my inbox; time-block my top three tasks; start, check or "
            "stop a Pomodoro; prepare me for a meeting; send a reply to a sender; remember a preference; "
            "what should I know before I plan a day; list, add or complete a task; is my week "
            "over-booked; wrap up my day; run my weekly review; note something. "
            "Set ANTHROPIC_API_KEY to talk to Claude instead.")


SCRIPTS: dict[str, Callable[[Slot], str | None]] = {
    "morning_brief": morning_brief, "triage": triage, "time_block": time_block,
    "pomodoro_start": pomodoro_start, "pomodoro_stop": pomodoro_stop, "pomodoro_status": pomodoro_status,
    "focus_end": focus_end, "remember": remember, "recall": recall, "weekly_review": weekly_review,
    "end_of_day": end_of_day, "meeting_prep": meeting_prep, "vip_alert": vip_alert,
    "send_reply": send_reply, "task_add": task_add, "task_done": task_done, "task_list": task_list,
    "agenda": agenda, "week_load": week_load, "capture": capture, "help": help_,
}


def _learned_skill(request: str) -> str | None:
    """A live skill that was learned, when it is the best match for the request.

    The authored skills are loaded by their own scripts above. A learned skill has no script,
    so the responder loads it here, at the start of the turn, by the same keyword ranking the
    Skills chapter shows.
    """
    ranked = skills.rank(request)
    if ranked and ranked[0]["name"] not in skills.SKILLS:
        return ranked[0]["name"]
    return None


def respond(messages: list[Any]) -> AIMessage:
    """One step of the scripted loop: either the next tool calls or the final answer."""
    human, results = _turn(messages)
    request = human.additional_kwargs.get("request", "")
    intents = detect(request, human.additional_kwargs.get("trigger", "chat"))
    pending: list[dict[str, Any]] = []
    answers = []
    for index, (name, text) in enumerate(intents):
        slot = Slot(index, text, results)
        slot.pending = pending
        try:
            answer = SCRIPTS[name](slot)
        except (KeyError, TypeError, IndexError):
            # A tool result did not have the shape the script expects, as after a declined action.
            answer = "I could not finish this request: an action was declined or returned nothing to report."
        if answer is not None:
            answers.append(answer)
    learned = _learned_skill(request) if not results else None
    if learned and not any(call["name"] == "load_skill" for call in pending):
        pending.insert(0, {"type": "tool_call", "name": "load_skill", "args": {"name": learned},
                           "id": "learned_load_skill_1"})
    metadata = {"stop_reason": "tool_use" if pending else "end_turn", "model_name": LABEL,
                "intents": [name for name, _ in intents]}
    if pending:
        return AIMessage(content="", tool_calls=pending, response_metadata=metadata)
    return AIMessage(content="\n\n".join(answers), response_metadata=metadata)
