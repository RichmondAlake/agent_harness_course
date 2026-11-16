"""Trusted tools: what the model may call, and what each call is allowed to cause.

The model never reaches an MCP server directly. Every tool here is a harness
function with a typed schema and an effect tier. Reads delimit external text
before it reaches the model; writes are logged with a reason; gated writes are
drafted, shown to a person and executed only after approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

import policy
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.core import (approval, calendar_intel, clock, focus, inbox, review, scratchfs, skills,
                          store, tasks, websearch, world)
from backend.core.memory import memory_provider
from backend.core.workspace import ALLOWLIST, WorkspaceError, workspace

REASON = Field(description="One plain sentence for the owner's action log: why this action helps.")
HISTORY_MESSAGES, HISTORY_CHARACTERS = 5, 2000


@dataclass(frozen=True)
class ToolContext:
    """Where a call came from, so its effects can be traced back."""
    thread_id: str
    session_id: str
    run_id: str | None = None
    origin: str = "agent"


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(Args):
    pass


# ── Argument schemas ─────────────────────────────────────────────────────────

class SearchThreads(Args):
    query: str = Field("", description="Words that must all appear. Empty lists everything.")
    label: Literal["INBOX", "SENT", "ALL"] = Field(
        "INBOX", description="INBOX is recent mail, SENT is mail the owner sent, ALL is the whole history.")
    max_results: int = Field(10, ge=1, le=25)


class ThreadRef(Args):
    thread_id: str


class Draft(Args):
    to: list[str] = Field(min_length=1)
    subject: str
    body: str
    thread_id: str = Field("", description="The thread being answered, when there is one.")
    reason: str = REASON


class Send(Draft):
    cc: list[str] = Field(default_factory=list)


class EventRange(Args):
    start_date: str = Field(description="ISO date, for example 2001-08-07.")
    end_date: str = Field("", description="ISO date, inclusive. Defaults to the start date.")


class CreateEvent(Args):
    title: str
    start: str = Field(description="ISO datetime with offset.")
    end: str = Field(description="ISO datetime with offset.")
    attendees: list[str] = Field(default_factory=list, description="Leave empty for a block only the owner sees.")
    description: str = ""
    kind: Literal["focus", "meeting", "personal"] = "focus"
    reason: str = REASON

    @model_validator(mode="after")
    def _ordered(self) -> "CreateEvent":
        """Both moments must parse, carry the owner's offset when none is given, and be in order."""
        start, end = clock.localise(self.start), clock.localise(self.end)
        if end <= start:
            raise ValueError("end must be after start")
        self.start, self.end = start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")
        return self


class Respond(Args):
    event_id: str
    response: Literal["accepted", "declined", "tentative"]
    comment: str = ""
    reason: str = REASON


class NotesQuery(Args):
    query: str = ""


class PageRef(Args):
    page_id: str


class CreatePage(Args):
    title: str
    body: str
    reason: str = REASON


class AppendPage(Args):
    page_id: str
    text: str
    reason: str = REASON


class TaskList(Args):
    status: Literal["OPEN", "DONE", "ALL"] = "OPEN"


class TaskAdd(Args):
    title: str
    priority: int = Field(3, ge=1, le=4, description="1 is highest.")
    due_at: str | None = Field(None, description="ISO datetime, only when a date was stated.")
    est_pomodoros: int = Field(1, ge=1, le=8)
    source_type: Literal["mail", "notes", "calendar", "chat", "capture"] = "chat"
    source_ref: str | None = Field(None, description="The thread, page or event ID this task came from.")
    reason: str = REASON


class TaskUpdate(Args):
    task_id: str
    title: str | None = None
    priority: int | None = Field(None, ge=1, le=4)
    due_at: str | None = None
    est_pomodoros: int | None = Field(None, ge=1, le=8)
    reason: str = REASON


class TaskRef(Args):
    task_id: str
    reason: str = REASON


class TaskSnooze(Args):
    task_id: str
    until: str = Field(description="ISO datetime. The task is hidden from the list until then.")
    reason: str = REASON


class DayRef(Args):
    date: str | None = Field(None, description="ISO date. Defaults to today on the harness clock.")


class WeekRef(Args):
    start_date: str | None = None
    days: int = Field(5, ge=1, le=10)


class PlanBlocks(Args):
    task_ids: list[str] = Field(default_factory=list,
                                description="Tasks to place, in order. Empty means the top three.")
    date: str | None = None
    reason: str = REASON


class EventRef(Args):
    event_id: str


class PomodoroStart(Args):
    task_id: str | None = None
    minutes: int | None = Field(None, description="Between 5 and 90. Defaults to the owner's setting.")
    reason: str = REASON


class PomodoroStop(Args):
    reason: str = REASON


class FocusRef(Args):
    session_id: str


class Capture(Args):
    text: str


class ScratchWrite(Args):
    path: str = Field(description="For example /plans/today.md or /notes/ideas.md")
    content: str
    promote_on_end: bool = Field(False, description="Promote when the workday ends.")
    promote_target: Literal["task", "memory"] = "memory"


class ScratchRead(Args):
    path: str


class MemoryWrite(Args):
    memory_type: Literal["preference", "guideline", "fact", "person", "commitment"]
    content: str = Field(description="One self-contained sentence.")
    ttl_days: int | None = Field(None, ge=1, le=730)
    reason: str = REASON


class MemorySearch(Args):
    query: str
    limit: int = Field(8, ge=1, le=20)


class SkillRef(Args):
    name: str


class WorkdayEnd(Args):
    reason: str = REASON


class WebSearch(Args):
    query: str
    max_results: int = Field(5, ge=1, le=8)


class ContactQuery(Args):
    query: str = Field("", description="Part of a name or address. Empty lists VIPs first.")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _event_for_model(event: dict[str, Any]) -> dict[str, Any]:
    """Text an outside organiser wrote is data, so it is delimited."""
    shown = dict(event)
    if event.get("organizer", "").lower() != world.owner_email():
        for key in ("description", "location"):
            if shown.get(key):
                shown[key] = policy.wrap_untrusted("calendar", event["event_id"], shown[key])
    return shown


async def _refuse_quarantined(thread_id: str | None) -> dict[str, Any] | None:
    if not thread_id:
        return None
    row = await inbox.thread(thread_id)
    if row is None:
        return {"error": "unknown_thread", "detail": f"No thread has the ID {thread_id}."}
    if row["category"] == "quarantine":
        return {"error": "quarantined_thread",
                "detail": "This thread is quarantined. It is reported, never answered, forwarded or tracked."}
    return None


# ── Mail ─────────────────────────────────────────────────────────────────────

async def mail_search_threads(args: SearchThreads, ctx: ToolContext) -> dict[str, Any]:
    found = await workspace.call("mail_search_threads", args.model_dump())
    rows = [await inbox.thread(item["thread_id"]) for item in found.get("threads", [])]
    return {"label": args.label, "threads": [inbox.for_model(row) for row in rows if row],
            **({"note": found["note"]} if found.get("note") else {})}


async def mail_get_thread(args: ThreadRef, ctx: ToolContext) -> dict[str, Any]:
    row = await inbox.thread(args.thread_id)
    if row is None:
        return {"error": "thread_not_found", "thread_id": args.thread_id}
    shown = inbox.for_model(row, body=True)
    if row["category"] == "quarantine":
        return shown
    raw = await workspace.call("mail_get_thread", {"thread_id": args.thread_id})
    history = raw.get("thread", {}).get("messages", [])
    shown.update(to=row["to"], cc=row["cc"], participants=row["participants"],
                 message_count=len(history) or 1)
    if len(history) > 1:
        shown["earlier_messages"] = [{
            "from_email": item["from_email"], "sent_at": item["sent_at"],
            "shortened": len(item["body"]) > HISTORY_CHARACTERS,
            "content": policy.wrap_untrusted("mail", args.thread_id, item["body"][:HISTORY_CHARACTERS])}
            for item in history[-HISTORY_MESSAGES - 1:-1]]
    return shown


async def mail_create_draft(args: Draft, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("mail_create_draft", args.model_dump(exclude={"reason"}))


async def mail_list_drafts(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("mail_list_drafts", {})


async def mail_list_sent(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("mail_list_sent", {})


async def mail_send_message(args: Send, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("mail_send_message", args.model_dump(exclude={"reason"}))


# ── Calendar ─────────────────────────────────────────────────────────────────

async def calendar_list_events(args: EventRange, ctx: ToolContext) -> dict[str, Any]:
    events = await calendar_intel.events_between(clock.parse_day(args.start_date),
                                                 clock.parse_day(args.end_date or args.start_date))
    return {"events": [_event_for_model(item) for item in events], "timezone": world.persona()["timezone"]}


async def calendar_create_event(args: CreateEvent, ctx: ToolContext) -> dict[str, Any]:
    payload = args.model_dump(exclude={"reason"})
    payload["attendees"] = payload["attendees"] or [world.owner_email()]
    return await workspace.call("calendar_create_event", payload)


async def calendar_respond_to_event(args: Respond, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("calendar_respond_to_event", args.model_dump(exclude={"reason"}))


async def day_overview(args: DayRef, ctx: ToolContext) -> dict[str, Any]:
    overview = await calendar_intel.overview(clock.parse_day(args.date))
    return {**overview, "events": [_event_for_model(item) for item in overview["events"]],
            "meeting_rule_violations": [{"event_id": item["event_id"], "title": item["title"],
                                         "start": item["start"]}
                                        for item in overview["meeting_rule_violations"]]}


async def free_slots(args: DayRef, ctx: ToolContext) -> dict[str, Any]:
    overview = await calendar_intel.overview(clock.parse_day(args.date))
    return {"day": overview["day"], "free_slots": overview["free_slots"], "rules": overview["rules"]}


async def week_load(args: WeekRef, ctx: ToolContext) -> dict[str, Any]:
    loads = await calendar_intel.week(clock.parse_day(args.start_date), args.days)
    return {"days": loads, "overbooked_days": [item["day"] for item in loads if item["overbooked"]]}


async def plan_time_blocks(args: PlanBlocks, ctx: ToolContext) -> dict[str, Any]:
    result = await calendar_intel.plan(args.task_ids or None, clock.parse_day(args.date))
    return {key: result[key] for key in ("day", "blocks", "unplaced", "unknown_task_ids",
                                         "pomodoro_unit_minutes", "plan_path", "rule")}


async def meeting_prep(args: EventRef, ctx: ToolContext) -> dict[str, Any]:
    found = await calendar_intel.meeting_prep(args.event_id)
    if found is None:
        return {"error": "event_not_found", "event_id": args.event_id}
    page = found.get("related_page")
    return {"event": _event_for_model(found["event"]), "people": found["people"],
            "starts_in_minutes": found.get("starts_in_minutes"),
            "related_thread": inbox.for_model(found["related_thread"], body=True)
            if found.get("related_thread") else None,
            "related_page": {"page_id": page["page_id"], "title": page["title"], "shared": page["shared"],
                             "content": policy.wrap_untrusted("notes", page["page_id"], page["body"])}
            if page else None,
            "owner_actions": found.get("owner_actions", []),
            "earlier_threads": [{key: item.get(key) for key in
                                 ("thread_id", "from_email", "subject", "received_at", "message_count")}
                                for item in found.get("earlier_threads", [])],
            **({"error": found["error"]} if found.get("error") else {})}


# ── Notes ────────────────────────────────────────────────────────────────────

async def notes_search(args: NotesQuery, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("notes_search", args.model_dump())


async def notes_get_page(args: PageRef, ctx: ToolContext) -> dict[str, Any]:
    found = await workspace.call("notes_get_page", args.model_dump())
    page = found.get("page")
    if not page:
        return found
    return {"page_id": page["page_id"], "title": page["title"], "shared": page["shared"],
            "last_edited": page.get("last_edited"),
            "content": policy.wrap_untrusted("notes", page["page_id"], page["body"]),
            "owner_actions": policy.extract_actions(page["body"], world.owner_first_name())}


async def notes_create_page(args: CreatePage, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("notes_create_page", args.model_dump(exclude={"reason"}))


async def notes_append_to_page(args: AppendPage, ctx: ToolContext) -> dict[str, Any]:
    return await workspace.call("notes_append_to_page", args.model_dump(exclude={"reason"}))


async def _page_tier(args: AppendPage) -> str:
    """A private page is the owner's own; a shared page is seen by other people."""
    found = await workspace.call("notes_get_page", {"page_id": args.page_id})
    return "approval" if (found.get("page") or {}).get("shared", True) else "automatic"


# ── Tasks ────────────────────────────────────────────────────────────────────

async def triage_inbox(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    result = await inbox.triage()
    unknown = [row for row in result["rows"] if row["trust"] == "unknown"]
    return {"as_of": result["as_of"], "counts": result["counts"],
            "rows": [inbox.for_model(row) for row in result["rows"]],
            "unknown_senders": {"threads": len(unknown),
                                "flagged_by_tripwire": sum(bool(row["injection_patterns"]) for row in unknown)},
            "rule": result["rule"]}


def _task_view(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("task_id", "title", "status", "priority", "due_at", "urgent",
                                       "est_pomodoros", "source_type", "source_ref", "carry_over_count",
                                       "planned_for", "snoozed")}


async def task_list(args: TaskList, ctx: ToolContext) -> dict[str, Any]:
    if args.status == "OPEN":
        rows = tasks.governed()
    elif args.status == "DONE":
        rows = tasks.recently_done()
    else:
        rows = [*tasks.governed(include_snoozed=True), *tasks.recently_done()]
    health = tasks.health()
    return {"order": "urgent first, then priority, then due date", "count": len(rows),
            "tasks": [_task_view(item) for item in rows],
            "slipping": [item["task_id"] for item in health["slipping"]],
            "stale": [item["task_id"] for item in health["stale"]]}


async def task_add(args: TaskAdd, ctx: ToolContext) -> dict[str, Any]:
    if args.source_type == "mail":
        refused = await _refuse_quarantined(args.source_ref)
        if refused:
            return refused
    made = tasks.add(args.title, priority=args.priority, due_at=args.due_at,
                     est_pomodoros=args.est_pomodoros, source_type=args.source_type,
                     source_ref=args.source_ref)
    return {"status": made["status"], "task_id": made["task"]["task_id"],
            "task": _task_view(made["task"]), **({"message": made["message"]} if "message" in made else {})}


async def task_update(args: TaskUpdate, ctx: ToolContext) -> dict[str, Any]:
    changed = tasks.update(args.task_id, **args.model_dump(exclude={"task_id", "reason"}))
    return {"status": "updated", "task": _task_view(changed)}


async def task_complete(args: TaskRef, ctx: ToolContext) -> dict[str, Any]:
    return {"status": "completed", "task_id": args.task_id,
            "task": _task_view(tasks.set_status(args.task_id, "DONE"))}


async def task_snooze(args: TaskSnooze, ctx: ToolContext) -> dict[str, Any]:
    return {"status": "snoozed", "task": _task_view(tasks.update(args.task_id, snoozed_until=args.until))}


# ── Focus, scratch and memory ────────────────────────────────────────────────

async def pomodoro_start(args: PomodoroStart, ctx: ToolContext) -> dict[str, Any]:
    minutes = args.minutes or world.persona()["pomodoro_minutes"]
    clamped = min(max(minutes, focus.MIN_MINUTES), focus.MAX_MINUTES)
    started = focus.start(args.task_id, clamped)
    return {**started, "minutes": clamped,
            **({"note": f"{minutes} minutes is outside 5 to 90, so {clamped} was used."}
               if clamped != minutes else {})}


async def pomodoro_status(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    current = focus.running()
    if current is None:
        return {"status": "not_running"}
    return {"status": "running", "session": current,
            "distractions": [item["content"] for item in scratchfs.distractions(current["session_id"])]}


async def pomodoro_stop(args: PomodoroStop, ctx: ToolContext) -> dict[str, Any]:
    stopped = focus.stop(args.reason)
    if "distractions" in stopped:
        stopped["distractions"] = [item["content"] for item in stopped["distractions"]]
    return stopped


async def focus_session_report(args: FocusRef, ctx: ToolContext) -> dict[str, Any]:
    """Harness-only: what one finished session achieved."""
    session = focus.get(args.session_id)
    if session is None:
        return {"error": "unknown_session", "session_id": args.session_id}
    return {"session": session,
            "distractions": [item["content"] for item in scratchfs.distractions(session["session_id"])],
            "break_minutes": world.persona()["break_minutes"]}


async def capture_note(args: Capture, ctx: ToolContext) -> dict[str, Any]:
    captured = focus.distraction(args.text)
    return {"status": "captured", **{key: captured[key] for key in
                                     ("path", "kind", "session_id", "focus_session_id")},
            "promote_on_end": True, "promote_target": "task"}


async def scratch_write(args: ScratchWrite, ctx: ToolContext) -> dict[str, Any]:
    return scratchfs.begin_session(ctx.session_id).write(
        args.path, args.content, promote_on_end=args.promote_on_end, promote_target=args.promote_target)


async def scratch_read(args: ScratchRead, ctx: ToolContext) -> dict[str, Any]:
    try:
        return {"path": args.path, "content": scratchfs.ScratchFS(ctx.session_id).read(args.path)}
    except FileNotFoundError:
        return {"error": "file_not_found", "path": args.path}


async def scratch_list(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    return {"session_id": ctx.session_id, "files": [
        {key: item[key] for key in ("path", "kind", "promote_on_end", "promote_target", "promotion_state")}
        for item in scratchfs.ScratchFS(ctx.session_id).files("/")]}


def _memory_view(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in ("memory_id", "memory_type", "content", "created_at",
                                           "expires_at", "score")}


async def memory_write(args: MemoryWrite, ctx: ToolContext) -> dict[str, Any]:
    written = memory_provider.write(args.memory_type, args.content, ttl_days=args.ttl_days, metadata={
        "source": "stated_by_owner", "thread_id": ctx.thread_id, "session_id": ctx.session_id})
    return {"status": "already_known" if written["deduplicated"] else "remembered",
            "memory_id": written["memory_id"], "memory": _memory_view(written)}


async def memory_search(args: MemorySearch, ctx: ToolContext) -> dict[str, Any]:
    found = memory_provider.recall(args.query, limit=args.limit)
    return {"query": args.query, "memories": [_memory_view(item) for item in found],
            "standing": [_memory_view(item) for item in memory_provider.standing()]}


async def load_skill(args: SkillRef, ctx: ToolContext) -> dict[str, Any]:
    found = skills.load(args.name)
    return found or {"error": "unknown_skill", "available": [item["name"] for item in skills.manifests()]}


# ── Reviews and the wider world ──────────────────────────────────────────────

async def weekly_review_data(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    return review.weekly()


async def end_of_day_data(args: NoArgs, ctx: ToolContext) -> dict[str, Any]:
    return await review.end_of_day()


async def end_workday(args: WorkdayEnd, ctx: ToolContext) -> dict[str, Any]:
    ended = scratchfs.end_session(ctx.session_id)
    return {key: ended[key] for key in ("session_id", "status", "staged", "promoted", "duplicates",
                                        "outcomes")} | {
        "carried_over": [{"task_id": item["task_id"], "title": item["title"],
                          "carry_over_count": item["carry_over_count"]} for item in ended["carried_over"]],
        "episode": ended["episode"]["content"]}


async def web_search(args: WebSearch, ctx: ToolContext) -> dict[str, Any]:
    return await websearch.search(args.query, args.max_results)


async def contacts_lookup(args: ContactQuery, ctx: ToolContext) -> dict[str, Any]:
    needle = args.query.lower().strip()
    found = [item for item in store.contacts()
             if not needle or needle in item["name"].lower() or needle in item["email"]]
    return {"count": len(found), "contacts": [
        {key: item[key] for key in ("name", "email", "organisation", "role", "relationship", "is_vip")}
        for item in found[:15]],
        "rule": "VIP status is derived from the mail the owner sends; it is read here, never guessed."}


# ── Registry ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[Args]
    handler: Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]
    tier: str = "automatic"          # automatic | approval | conditional
    effect: bool = False             # writes something, so it belongs in the action log
    source: str = "harness"          # harness | mcp:mail | mcp:calendar | mcp:notes | web
    model_facing: bool = True


def _mcp(name: str, description: str, args: type[Args], handler: Callable, *, effect: bool = False) -> Tool:
    return Tool(name, description, args, handler, tier=ALLOWLIST[name], effect=effect,
                source="mcp:" + name.split("_", 1)[0])


TOOLS: dict[str, Tool] = {tool.name: tool for tool in (
    _mcp("mail_search_threads", "List mail threads, newest first, each with its governed signals.",
         SearchThreads, mail_search_threads),
    _mcp("mail_get_thread", "Read one mail thread in full. A quarantined thread is withheld.",
         ThreadRef, mail_get_thread),
    _mcp("mail_create_draft", "Save a message as a draft. Nothing is sent and nobody is notified.",
         Draft, mail_create_draft, effect=True),
    _mcp("mail_list_drafts", "List drafts saved through the assistant.", NoArgs, mail_list_drafts),
    _mcp("mail_list_sent", "List messages sent through the assistant.", NoArgs, mail_list_sent),
    _mcp("mail_send_message", "Send mail to other people. Pauses for the owner's approval.",
         Send, mail_send_message, effect=True),
    _mcp("calendar_list_events", "List calendar events between two dates, inclusive.",
         EventRange, calendar_list_events),
    _mcp("calendar_create_event", "Create a calendar event. Pauses for the owner's approval.",
         CreateEvent, calendar_create_event, effect=True),
    _mcp("calendar_respond_to_event", "Accept, decline or tentatively accept an invitation. "
                                      "Pauses for the owner's approval.",
         Respond, calendar_respond_to_event, effect=True),
    _mcp("notes_search", "Find pages by title or content.", NotesQuery, notes_search),
    _mcp("notes_get_page", "Read one page and the owner's open actions on it.", PageRef, notes_get_page),
    _mcp("notes_create_page", "Create a private page that only the owner can see.",
         CreatePage, notes_create_page, effect=True),
    _mcp("notes_append_to_page", "Append text to a page. On a shared page this pauses for approval.",
         AppendPage, notes_append_to_page, effect=True),
    Tool("triage_inbox", "Apply governed triage to the inbox: category, VIP, tracking and quarantine "
                         "for every thread, in attention order.", NoArgs, triage_inbox),
    Tool("task_list", "List tasks in governed order, with urgent, slipping and stale marked.",
         TaskList, task_list),
    Tool("task_add", "Add a task. An open task that already covers the same source is returned instead.",
         TaskAdd, task_add, effect=True),
    Tool("task_update", "Change a task's title, priority, due date or estimate.",
         TaskUpdate, task_update, effect=True),
    Tool("task_complete", "Mark a task done.", TaskRef, task_complete, effect=True),
    Tool("task_snooze", "Hide a task from the list until a given moment.", TaskSnooze, task_snooze, effect=True),
    Tool("day_overview", "One day: events, free slots, broken meeting rules and load.",
         DayRef, day_overview),
    Tool("free_slots", "Free slots for a day, by the governed definition of free.", DayRef, free_slots),
    Tool("week_load", "Meeting load for the coming working days, with over-booked days flagged.",
         WeekRef, week_load),
    Tool("plan_time_blocks", "Place tasks into a day's free slots and write the plan to /plans/today.md. "
                             "Writes nothing to the calendar.", PlanBlocks, plan_time_blocks, effect=True),
    Tool("meeting_prep", "Gather what is known about one meeting: people, thread, page, open actions.",
         EventRef, meeting_prep),
    Tool("pomodoro_start", "Start a focus session tied to a task and arm its timer.",
         PomodoroStart, pomodoro_start, effect=True),
    Tool("pomodoro_status", "The running focus session, time left and parked distractions.",
         NoArgs, pomodoro_status),
    Tool("pomodoro_stop", "Stop the running focus session early.", PomodoroStop, pomodoro_stop, effect=True),
    Tool("capture_note", "Quick capture into the scratch inbox. During a focus session it is parked "
                         "as a distraction.", Capture, capture_note, effect=True),
    Tool("scratch_write", "Write a working file for this workday.", ScratchWrite, scratch_write, effect=True),
    Tool("scratch_read", "Read a working file from this workday.", ScratchRead, scratch_read),
    Tool("scratch_list", "List this workday's working files.", NoArgs, scratch_list),
    Tool("memory_write", "Save something durable the owner stated or confirmed.",
         MemoryWrite, memory_write, effect=True),
    Tool("memory_search", "Search long-term memory.", MemorySearch, memory_search),
    Tool("load_skill", "Load the full procedure for one skill named in the context.", SkillRef, load_skill),
    Tool("weekly_review_data", "Planned versus done, time by task, slipping tasks and drop candidates.",
         NoArgs, weekly_review_data),
    Tool("end_of_day_data", "Done today, carried over, and tomorrow's first free slot.",
         NoArgs, end_of_day_data),
    Tool("end_workday", "End the workday session: promote marked notes and count slips.",
         WorkdayEnd, end_workday, effect=True),
    Tool("web_search", "Search the web. Results are external text.", WebSearch, web_search, source="web"),
    Tool("contacts_lookup", "Look up people the owner writes to, with VIP status.",
         ContactQuery, contacts_lookup),
    Tool("focus_session_report", "What one finished focus session achieved.", FocusRef,
         focus_session_report, model_facing=False),
)}


def schemas() -> list[dict[str, Any]]:
    """Tool definitions for the model. The list is fixed for the life of a conversation."""
    definitions = []
    for tool in TOOLS.values():
        if tool.model_facing:
            schema = tool.args.model_json_schema()
            schema.pop("title", None)
            definitions.append({"name": tool.name, "description": tool.description, "input_schema": schema})
    return definitions


def sync_registry() -> None:
    """Mirror every tool, reachable or not, into ``ppa_tool_registry``."""
    stamp = store.real_now()
    store.execute("DELETE FROM ppa_tool_registry", trace=False)
    rows = [(tool.name, tool.source, tool.tier, int(tool.model_facing), tool.description,
             store.dumps(tool.args.model_json_schema())) for tool in TOOLS.values()]
    for system, offered in workspace.catalogue().items():
        rows += [(item["name"], f"mcp:{system}", "never", 0, item["description"],
                  store.dumps(item["input_schema"])) for item in offered if not item["exposed"]]
    for item in rows:
        store.execute("INSERT OR REPLACE INTO ppa_tool_registry VALUES (?,?,?,?,?,?,?)", (*item, stamp),
                      trace=False)


def validate(name: str, arguments: dict[str, Any]) -> Args:
    tool = TOOLS.get(name)
    if tool is None:
        if workspace.tier(name) == "never" and any(
                item["name"] == name for items in workspace.catalogue().values() for item in items):
            raise PermissionError(f"{name} exists on the server but is not on the harness allowlist.")
        raise KeyError(f"{name} is not a tool this assistant has.")
    return tool.args(**arguments)


async def refusal(name: str, args: Args) -> dict[str, Any] | None:
    """A reason to refuse a call outright, before it is run or drafted."""
    if name in {"mail_send_message", "mail_create_draft"}:
        return await _refuse_quarantined(args.thread_id)
    return None


async def tier_for(name: str, args: Args) -> str:
    tool = TOOLS[name]
    return await _page_tier(args) if tool.tier == "conditional" else tool.tier


async def execute(name: str, args: Args, ctx: ToolContext) -> dict[str, Any]:
    """Run one validated tool. The caller has already settled its tier."""
    try:
        return await TOOLS[name].handler(args, ctx)
    except WorkspaceError as exc:
        return {"error": "workspace_failed", "detail": str(exc)}
    except (KeyError, ValueError, FileNotFoundError) as exc:
        return {"error": type(exc).__name__, "detail": str(exc).strip("'\"")}


async def run(name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Validate and run an automatic tool, logging its effect. Gated tools are refused here."""
    try:
        args = validate(name, arguments)
    except ValidationError as exc:
        return {"error": "invalid_arguments", "detail": exc.errors(include_url=False, include_input=False)}
    except (KeyError, PermissionError) as exc:
        return {"error": "tool_not_available", "detail": str(exc).strip("'\"")}
    if await tier_for(name, args) == "approval":
        return {"error": "approval_required",
                "detail": f"{name} is seen by other people, so it needs the owner's approval."}
    result = await refusal(name, args) or await execute(name, args, ctx)
    if TOOLS[name].effect:
        approval.record(name, args.model_dump(), result, reason=getattr(args, "reason", ""),
                        thread_id=ctx.thread_id, session_id=ctx.session_id, run_id=ctx.run_id,
                        origin=ctx.origin)
    return result


def catalogue() -> list[dict[str, Any]]:
    return [{"name": tool.name, "description": tool.description, "tier": tool.tier, "effect": tool.effect,
             "source": tool.source, "model_facing": tool.model_facing} for tool in TOOLS.values()]
