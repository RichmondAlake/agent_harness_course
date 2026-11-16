"""The teaching frame of every chapter, as data.

Each chapter page opens with the same frame: what the thing is, why the
harness needs it, the terms it uses, one small diagram, steps to try on the
page, what to take away, and the Part of the notebook it matches. The page
draws the frame from this module, so a chapter cannot leave a section out
and a test can check that none does.

A diagram is a list of nodes on a grid and a list of labelled arrows. The page
draws it as inline SVG. ``row`` runs top to bottom and ``col`` left to right.
``kind`` picks the small swatch on a node: person, harness, model, store, gate
or outside.
"""
from __future__ import annotations

from typing import Any

NOTEBOOK = "../notebook/ppa_custom_harness.ipynb"
PARTS: dict[int, str] = {
    1: "Setup: environment, database and an embedding model", 2: "The practice week",
    3: "Systems of record, reached through MCP", 4: "What the harness owns: state and governed meaning",
    5: "Memory: a scratch space for the day, and Oracle Agent Memory",
    6: "Skills with versions, and a runtime for time", 7: "System One: a second model that decides",
    8: "Trusted tools", 9: "Claude: adaptive thinking, a cached prompt and a price on every call",
    10: "The control loop, with approval inside it", 11: "One working day, live, and what it cost",
    12: "Proactive behaviour and the weekly review", 13: "Learning from its own traces",
    14: "Evidence, scorecard and final acceptance",
}
FIELDS = ("what", "why", "terms", "diagram", "try", "takeaways", "notebook")
NODE_KINDS = ("person", "harness", "model", "store", "gate", "outside")

PRIMER = {
    "ppa": {
        "title": "What PPA is",
        "text": "PPA is a personal productivity assistant. It works for the owner of one mailbox. It "
                "reads mail and the calendar, turns requests into tasks, plans the day into free time, "
                "runs focus timers and briefs you before you ask. It sends mail or books a meeting only "
                "with your approval.",
        "does": ["reads mail and calendar", "turns requests into tasks", "plans the day into free time",
                 "runs focus timers", "briefs you before you ask", "sends or books only with your approval"],
    },
    "harness": {
        "title": "What a harness is",
        "text": "A harness is the runtime around the model. The model reasons and writes. The harness "
                "decides everything else.",
        "decides": [
            {"question": "What context is admitted", "answer": "which text reaches the model, and how it is marked"},
            {"question": "Which tools can run", "answer": "an allowlist, with a tier for each tool"},
            {"question": "When a person must approve", "answer": "anything another person will see"},
            {"question": "What is remembered", "answer": "long-term memory, and notes that last one workday"},
            {"question": "What evidence is kept", "answer": "every action, every run and every model call"},
        ],
    },
    "how_to_read": "The Assistant page is the product. Each numbered chapter opens one part of the "
                   "harness on the same running system, so what you do here shows up there.",
}


def _n(identity: str, label: str, row: int, col: int = 0, kind: str = "harness", note: str = "") -> dict[str, Any]:
    return {"id": identity, "label": label, "note": note, "row": row, "col": col, "kind": kind}


def _e(source: str, target: str, label: str) -> dict[str, str]:
    return {"from": source, "to": target, "label": label}


def _d(caption: str, nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> dict[str, Any]:
    return {"caption": caption, "nodes": nodes, "edges": edges}


def _t(term: str, definition: str) -> dict[str, str]:
    return {"term": term, "definition": definition}


def _s(do: str, watch: str) -> dict[str, str]:
    return {"do": do, "watch": watch}


CHAPTERS: dict[str, dict[str, Any]] = {
    "assistant": {
        "what": "This page is the assistant itself: a chat, today's calendar, the task list, the day plan "
                "and the timers. Every request you type runs through the whole harness.",
        "why": "PPA acts in the owner's name on mail that strangers can write. The page shows the two "
               "things that make that safe to use: what the assistant did on its own, and what it "
               "stopped to ask about.",
        "terms": [_t("Harness", "The runtime around the model: it admits context, runs tools, asks for "
                                "approval, remembers and keeps evidence."),
                  _t("Turn", "One request and everything the assistant does to answer it."),
                  _t("Approval card", "A drafted action shown to the owner, who approves or declines it "
                                      "before anything happens.")],
        "diagram": _d("One turn, from the request to the answer.", [
            _n("owner", "You type a request", 0, 0, "person"),
            _n("context", "Harness assembles context", 1, 0, "harness", "clock, memory, skills, rules"),
            _n("model", "Model plans", 2, 0, "model", "text and tool calls"),
            _n("tools", "Reads run at once", 3, 0, "harness", "mail, calendar, tasks"),
            _n("gate", "Outward actions wait", 3, 1, "gate", "approval card"),
            _n("answer", "Answer and trace", 4, 0, "store", "kept as evidence")],
            [_e("owner", "context", "request"), _e("context", "model", "prompt"),
             _e("model", "tools", "tool calls"), _e("model", "gate", "send, book"),
             _e("tools", "answer", "results"), _e("gate", "answer", "your decision")]),
        "try": [_s("Press the starter \"Prepare my morning brief.\"",
                   "The trace under the answer lists the tools that ran. All of them only read."),
                _s("Type \"Send a reply to\" and the name of a sender in the brief.",
                   "The run stops and an approval card appears. Nothing has been sent."),
                _s("Decline the card and type a reason.",
                   "The answer says the reply was not sent. The reason is kept with the turn."),
                _s("Open the data explorer at the foot of the page and choose ppa_turns.",
                   "One row for each turn you ran, with its outcome.")],
        "takeaways": ["The assistant reads on its own and asks before anything reaches another person.",
                      "Every turn leaves a record: what was asked, what ran and how it ended.",
                      "The chapters show the same running system, one part at a time."],
        "notebook": [10, 11],
    },
    "architecture": {
        "what": "A map of every part of the system and how they connect. Each part has a live status, "
                "checked while you look.",
        "why": "PPA touches mail, a calendar, timers and a model. Before changing one part you need to "
               "know which other parts a request passes through.",
        "terms": [_t("Component", "One part with one job: a node of the loop, a service, a table or a server."),
                  _t("System of record", "Where a kind of data really lives: the mail server, the calendar, "
                                         "the notes app."),
                  _t("Control loop", "The fixed sequence a turn follows: assemble context, call the model, "
                                     "run tools, ask for approval, save.")],
        "diagram": _d("Who owns what.", [
            _n("owner", "Owner", 0, 0, "person", "asks and approves"),
            _n("harness", "Harness", 1, 0, "harness", "loop, tools, gate, clock"),
            _n("store", "Harness store", 2, 0, "store", "tasks, memory, audit, traces"),
            _n("model", "Models", 2, 1, "model", "reason and decide"),
            _n("world", "Mail, calendar, notes", 2, 2, "outside", "reached through MCP")],
            [_e("owner", "harness", "requests, decisions"), _e("harness", "store", "state it owns"),
             _e("harness", "model", "context, tools"), _e("harness", "world", "allowlisted calls")]),
        "try": [_s("Select a component in the reference architecture.",
                   "The side panel names its technology, its tables, its endpoints and its files."),
                _s("Press \"Trace a request\" and then \"Play\".",
                   "Components light up in the order one request reaches them."),
                _s("Read the status legend above the component map.",
                   "With no keys, the model shows as not configured and the scripted responder as a fallback.")],
        "takeaways": ["Mail, calendar and notes stay where they live. The harness reads them on demand.",
                      "The harness owns only what has no other home: tasks, memory, the action log, traces.",
                      "A status that is checked live is more useful than a diagram that is only drawn."],
        "notebook": [1, 10],
    },
    "systems_of_record": {
        "what": "Mail, calendar and notes are reached through MCP, a standard way to offer tools to a "
                "model. The servers offer more tools than an assistant should have. The harness keeps a "
                "list of the ones it allows.",
        "why": "A mail server can delete. PPA must never delete the owner's mail because a stranger's "
               "message asked it to. A tool that is not on the list cannot be called at all.",
        "terms": [_t("MCP", "Model Context Protocol: a standard for a server to describe tools and for a "
                            "client to call them."),
                  _t("Allowlist", "The harness's own list of tools that may be called. Anything else does "
                                  "not exist for the model."),
                  _t("Effect tier", "What a tool is allowed to cause: automatic, approval, or never exposed.")],
        "diagram": _d("What the allowlist does to a server's tools.", [
            _n("server", "MCP server offers tools", 0, 0, "outside", "read, send, delete"),
            _n("list", "Harness allowlist", 1, 0, "gate", "a tier for each tool"),
            _n("auto", "Automatic", 2, 0, "harness", "reads, drafts"),
            _n("ask", "Approval", 2, 1, "gate", "send, book"),
            _n("never", "Never exposed", 2, 2, "outside", "delete, share")],
            [_e("server", "list", "everything it has"), _e("list", "auto", "runs"),
             _e("list", "ask", "waits"), _e("list", "never", "cannot be reached")]),
        "try": [_s("Read the \"Effect tiers\" panel.", "Each tool is in exactly one tier."),
                _s("In \"Run a read tool live\", press \"Call through MCP\".",
                   "A real result comes back from the practice mailbox."),
                _s("In \"Reach for a tool that is never exposed\", try one.",
                   "The harness refuses before any server is asked.")],
        "takeaways": ["The server decides what is offered. The harness decides what exists.",
                      "Data stays in its system of record and is read when needed, not copied.",
                      "A refusal by the allowlist cannot be talked around by the model."],
        "notebook": [3, 8],
    },
    "memory_layer": {
        "what": "Two kinds of memory. Long-term memory holds what should outlast the day: preferences, "
                "people, commitments. The scratch pad holds working notes for one workday.",
        "why": "A preference you state on Monday must hold on Friday. Most of what is written during a "
               "day should be forgotten. Keeping the two apart stops memory filling with noise.",
        "terms": [_t("Long-term memory", "Facts the assistant keeps across conversations, each with a type "
                                         "and an expiry."),
                  _t("Scratch pad", "Working files that belong to one workday session."),
                  _t("Promotion", "Moving a marked note into long-term memory or the task list when the "
                                  "workday ends, once only.")],
        "diagram": _d("What lasts and what does not.", [
            _n("day", "Notes during the day", 0, 0, "harness", "captures, the day plan"),
            _n("end", "Workday ends", 1, 0, "gate", "only marked notes go on"),
            _n("memory", "Long-term memory", 2, 0, "store", "with an expiry"),
            _n("tasks", "Task list", 2, 1, "store"),
            _n("turn", "Every later turn", 3, 0, "model", "recalled into the prompt")],
            [_e("day", "end", "marked to keep"), _e("end", "memory", "promote once"),
             _e("end", "tasks", "promote once"), _e("memory", "turn", "recall")]),
        "try": [_s("In \"Remember something\", write a preference and press \"Write to long-term memory\".",
                   "It appears in the memory list with a type and an expiry."),
                _s("In \"Recall\", ask for it in different words and press \"Recall\".",
                   "The memory comes back with the words it matched."),
                _s("Capture a thought, mark it to keep, then press \"End the workday and promote\".",
                   "The promotion queue shows it promoted. Running it again creates no duplicate.")],
        "takeaways": ["Memory needs forgetting as much as it needs remembering.",
                      "Promotion is a decision at the end of the day, not a side effect of writing.",
                      "A content hash stops the same note being promoted twice."],
        "notebook": [5],
    },
    "governed_meaning": {
        "what": "Words such as urgent, free, VIP and over-booked have written definitions. The harness "
                "computes them from data. The model reports them and does not decide them.",
        "why": "If the model decides what urgent means, a stranger's email that says URGENT becomes "
               "urgent. A definition the harness owns cannot be changed by the text of a message.",
        "terms": [_t("Governed meaning", "A term whose definition is written down once and computed by "
                                         "code, the same way every time."),
                  _t("Naive reading", "Guessing a meaning from surface features, such as the word urgent "
                                      "in a subject line.")],
        "diagram": _d("One question, two ways to answer it.", [
            _n("q", "\"What is urgent?\"", 0, 0, "person"),
            _n("naive", "Naive reading", 1, 0, "outside", "words in the text"),
            _n("rule", "Written definition", 1, 1, "harness", "computed from data"),
            _n("wrong", "A stranger can steer it", 2, 0, "outside"),
            _n("right", "Same answer every time", 2, 1, "store", "a test can assert it")],
            [_e("q", "naive", "guess"), _e("q", "rule", "compute"),
             _e("naive", "wrong", "follows the text"), _e("rule", "right", "follows the rule")]),
        "try": [_s("Press each question under \"One question, two readings\".",
                   "The two panels answer the same question over the same live data, and differ."),
                _s("Read \"What it gets wrong here\" under the naive reading.",
                   "It names the cases the surface reading misses or invents."),
                _s("Read the table \"The definitions\".", "Each term names the code that decides it.")],
        "takeaways": ["A meaning the harness computes cannot be argued with by an email.",
                      "Definitions are text a person can read and a test can check.",
                      "The model's job is to report the meaning, not to invent it."],
        "notebook": [4],
    },
    "inbox_triage": {
        "what": "Every thread in the inbox gets a category from the governed rules: reply, task, "
                "delegate, tracked, archive or quarantine. Actionable threads become tasks that link "
                "back to the thread.",
        "why": "The inbox is where strangers reach PPA. Triage is the first place a hostile message can "
               "be held back, and the place where one request must become exactly one task.",
        "terms": [_t("Quarantine", "A thread that looks like an attack from an unknown sender. It is "
                                   "reported by ID and never opened, answered or forwarded."),
                  _t("Source link", "The thread ID stored on a task, so the task can be traced back and "
                                    "is not raised twice."),
                  _t("Tripwire", "A pattern check for instructions aimed at an assistant. It catches some "
                                 "attacks and is not a defence on its own.")],
        "diagram": _d("From a thread to a task, or to quarantine.", [
            _n("mail", "A thread arrives", 0, 0, "outside", "anyone can write"),
            _n("signals", "Governed signals", 1, 0, "harness", "sender trust, VIP, patterns"),
            _n("task", "Task with a source link", 2, 0, "store", "one for each thread"),
            _n("held", "Quarantine", 2, 1, "gate", "not opened")],
            [_e("mail", "signals", "read as data"), _e("signals", "task", "actionable"),
             _e("signals", "held", "looks like an attack")]),
        "try": [_s("Read the tiles at the top.", "They count threads by category, with quarantine among them."),
                _s("Press \"Extract all actionable\".",
                   "Tasks are created and drafts saved. The notice says none was sent."),
                _s("Press \"Extract all actionable\" again.",
                   "No new task: each thread is reported as covered by its existing task."),
                _s("Select a quarantined row.", "The thread opens for you, with the text hidden until you ask.")],
        "takeaways": ["Text from outside is data to sort, never instructions to follow.",
                      "A source link makes task creation safe to repeat.",
                      "Quarantine is decided by the harness before the model sees the text."],
        "notebook": [4, 8],
    },
    "calendar_intel": {
        "what": "Free time, broken meeting rules and over-booked days are computed from the calendar and "
                "the owner's working rules. Tasks are placed into free slots as proposed blocks.",
        "why": "Planning the day means writing to a calendar other people can see. PPA computes the plan "
               "itself, and asks before any event is created.",
        "terms": [_t("Free slot", "Time inside working hours with no event, by a written definition."),
                  _t("Time block", "A calendar event that protects time for one task."),
                  _t("Over-booked", "A day with more meeting minutes than the owner's limit.")],
        "diagram": _d("Planning is automatic. Writing to the calendar is not.", [
            _n("cal", "Events and working rules", 0, 0, "outside"),
            _n("free", "Free slots", 1, 0, "harness", "by definition"),
            _n("plan", "Blocks for the top tasks", 2, 0, "harness", "sized by estimate"),
            _n("gate", "Approval", 3, 0, "gate", "one card for each event"),
            _n("event", "Calendar event", 4, 0, "outside")],
            [_e("cal", "free", "compute"), _e("free", "plan", "fit tasks"),
             _e("plan", "gate", "draft events"), _e("gate", "event", "if approved")]),
        "try": [_s("Read \"Free by definition\".", "Each slot has a start, an end and a length."),
                _s("Press \"Plan the blocks\" under \"Time-block the top tasks\".",
                   "With no tasks yet it says so. Extract tasks in chapter 6 and try again."),
                _s("Press \"Plan and draft calendar events\".",
                   "Approval cards appear. No event exists until you approve one.")],
        "takeaways": ["The harness computes free time. The model does not estimate it.",
                      "A plan is a private note. A calendar event is an outward action.",
                      "Each day is judged against the owner's own limits."],
        "notebook": [4, 8],
    },
    "focus_sessions": {
        "what": "A focus session is a timer tied to a task. Starting one writes a row and arms a job on "
                "the real clock. Thoughts that interrupt you are parked until the break.",
        "why": "A timer that lives only in the browser is lost when the page closes. PPA keeps the timer "
               "in its store, so it still fires after a restart.",
        "terms": [_t("Focus session", "One timed period of work on one task, with planned and actual minutes."),
                  _t("Armed job", "A row that says what must happen and when. A scheduler fires it."),
                  _t("Parked distraction", "A thought captured during a session and shown again at the break.")],
        "diagram": _d("A timer that survives a restart.", [
            _n("start", "Start a session", 0, 0, "person"),
            _n("row", "Session row and armed job", 1, 0, "store", "in the harness store"),
            _n("fire", "Scheduler fires the job", 2, 0, "harness", "on the real clock"),
            _n("note", "Notification", 3, 0, "person", "minutes done, what was parked")],
            [_e("start", "row", "write"), _e("row", "fire", "when due"), _e("fire", "note", "report")]),
        "try": [_s("Type a short length in the minutes field and press \"Start the session\".",
                   "A countdown starts and the session log gains a row."),
                _s("Type a thought and press \"Park it\".", "It is listed under \"Parked during this session\"."),
                _s("Press \"Stop early\".", "The log records the actual minutes and that it was interrupted.")],
        "takeaways": ["Time is state. A timer is a row plus a job, not a variable.",
                      "What is recorded here is what the weekly review can report.",
                      "Parking a thought protects the session without losing the thought."],
        "notebook": [4, 6],
    },
    "skills": {
        "what": "A skill is a written procedure for one kind of request, such as the morning brief. "
                "Every turn carries one line for each skill. The full procedure is loaded only when it "
                "is needed.",
        "why": "PPA has many procedures and each is long. Sending all of them on every turn costs tokens "
               "and attention. Loading one on demand keeps each turn small.",
        "terms": [_t("Skill", "A named procedure the model can load and follow."),
                  _t("Manifest", "The name and one-line description of a skill. It is always in the prompt."),
                  _t("Progressive disclosure", "Showing a little first and loading the detail only when asked.")],
        "diagram": _d("One line always, one procedure on demand.", [
            _n("all", "Manifests of live skills", 0, 0, "store", "one line each"),
            _n("turn", "Every turn", 1, 0, "model", "sees the lines"),
            _n("load", "load_skill", 2, 0, "harness", "a tool call"),
            _n("body", "One full procedure", 3, 0, "store", "from the registry")],
            [_e("all", "turn", "always"), _e("turn", "load", "when one matches"),
             _e("load", "body", "read"), ]),
        "try": [_s("Press an example request, then \"Retrieve and disclose\".",
                   "Column 2 ranks the manifests. Column 3 shows the one procedure that was loaded."),
                _s("Read \"What the context pays\".",
                   "Three bars compare every procedure in every turn with loading one."),
                _s("Select a different manifest in column 1.", "Its procedure and the hash of its text are shown.")],
        "takeaways": ["A manifest costs a line. A procedure costs a page. Pay for the page only when used.",
                      "Skills live in a registry with a version and a hash, so a change is visible.",
                      "Only live skills are offered to the model. Chapter 16 shows how one becomes live."],
        "notebook": [6],
    },
    "approvals": {
        "what": "Reading runs on its own. Anything another person will see is drafted, shown to the "
                "owner with its risks, and run only after a decision. Every effect is written to an "
                "action log.",
        "why": "PPA sends mail and books meetings in the owner's name. A model can be wrong, and a "
               "message can be an attack. The gate puts a person between the model and other people.",
        "terms": [_t("Approval gate", "The point where a run pauses until the owner approves or declines "
                                      "a drafted action."),
                  _t("Action log", "One row for each effect: the tool, the reason, the decision and what "
                                   "was really delivered."),
                  _t("Untrusted content", "Text written by someone else. It is wrapped and marked as data "
                                          "before the model sees it.")],
        "diagram": _d("The life of a gated action.", [
            _n("call", "Model calls a gated tool", 0, 0, "model"),
            _n("draft", "DRAFTED", 1, 0, "store", "with a risk assessment"),
            _n("you", "Owner decides", 2, 0, "person"),
            _n("run", "APPROVED, then EXECUTED", 3, 0, "harness", "delivery recorded apart"),
            _n("no", "REJECTED", 3, 1, "gate", "the model is told, and adapts")],
            [_e("call", "draft", "not run"), _e("draft", "you", "approval card"),
             _e("you", "run", "approve"), _e("you", "no", "decline")]),
        "try": [_s("In \"Draft a gated action by hand\", press \"Draft it\".",
                   "The action appears under \"Waiting for a decision\". Nothing has happened yet."),
                _s("Decline it.", "The action log shows REJECTED and \"not executed\"."),
                _s("In \"Untrusted content\", press \"Show what the model receives\".",
                   "The text is wrapped and the patterns the tripwire sees are named.")],
        "takeaways": ["The audit row is the gate. An action runs only if its row says APPROVED.",
                      "Approval and delivery are recorded apart, because safe mode can hold what was approved.",
                      "A declined action goes back to the model as a result, so it adapts and does not retry."],
        "notebook": [8, 10, 11],
    },
    "the_loop": {
        "what": "The loop is the fixed path every turn follows: assemble context, call the model, run "
                "tools, pause for approval when needed, and save. Its state is saved after every step.",
        "why": "An approval may take minutes or days. The run must wait without losing its place, and "
               "continue from the same point after a restart.",
        "terms": [_t("Checkpoint", "The saved state of a run after one step, from which it can continue."),
                  _t("Interrupt", "A pause inside the loop that waits for a person and then resumes the "
                                  "same run."),
                  _t("Append-only context", "The prompt only ever grows. Earlier text is never rewritten.")],
        "diagram": _d("The loop, with approval inside it.", [
            _n("ctx", "assemble_context", 0, 0, "harness"),
            _n("model", "call_model", 1, 0, "model"),
            _n("tools", "dispatch_tools", 2, 0, "harness", "automatic tools run"),
            _n("save", "persist", 2, 2, "store", "answer, trace, trajectory"),
            _n("gate", "human_review", 3, 1, "gate", "pause and resume")],
            [_e("ctx", "model", "prompt"), _e("model", "tools", "tool calls"),
             _e("tools", "model", "results"), _e("tools", "gate", "gated tools"),
             _e("gate", "model", "decision"), _e("model", "save", "no more calls")]),
        "try": [_s("Read \"The graph\".", "The nodes the last turn passed through are marked."),
                _s("Type a request under \"What is assembled for a request\" and press \"Assemble\".",
                   "The stable prefix and the first user message are shown. No model is called."),
                _s("Select a run under \"Recent runs\".", "Its trace lists every node and tool with its time.")],
        "takeaways": ["The loop is code you can read, not behaviour you hope for.",
                      "A checkpoint after every step is what lets a run wait for a person.",
                      "A prompt that only grows keeps the cache and the model's earlier reasoning valid."],
        "notebook": [9, 10],
    },
    "routines": {
        "what": "Work the assistant starts itself: a morning brief, an end-of-day wrap, a weekly review, "
                "meeting preparation and an alert for mail from a VIP. Each is a job in a queue.",
        "why": "An assistant that waits to be asked misses the meeting in twenty minutes. Scheduled work "
               "enters through the same loop as a typed request, so the same gates apply.",
        "terms": [_t("Routine", "A request the harness makes on a schedule."),
                  _t("Event trigger", "A condition the harness checks, such as a meeting about to start, "
                                      "that starts a run."),
                  _t("Automation queue", "The table of jobs: what, when and in which state.")],
        "diagram": _d("Time starts a turn the same way a person does.", [
            _n("clock", "Schedule or event", 0, 0, "harness"),
            _n("queue", "Job in the queue", 1, 0, "store", "armed, then fired"),
            _n("loop", "The same loop", 2, 0, "harness", "same tools, same gate"),
            _n("note", "Notification", 3, 0, "person")],
            [_e("clock", "queue", "arm"), _e("queue", "loop", "fire"), _e("loop", "note", "deliver")]),
        "try": [_s("Press \"Start a 10-second timer\".", "A job is armed, counts down, fires and reports."),
                _s("Press \"Run now\" on the morning brief.", "A notification arrives, produced by a full turn."),
                _s("Press \"Simulate five working days\".",
                   "The week's routines run on the practice clock, with their notifications.")],
        "takeaways": ["Proactive work is a scheduled request, not a separate system.",
                      "A job that is a row survives a restart and can be shown with a countdown.",
                      "A routine cannot skip the approval gate."],
        "notebook": [6, 12],
    },
    "weekly_review": {
        "what": "A review of the week from what the harness recorded: tasks planned and done, focus "
                "minutes by task, what keeps slipping and what to drop.",
        "why": "PPA plans the owner's time. The review is how the owner sees whether the plans held, "
               "from records and not from the model's impression.",
        "terms": [_t("Carry-over", "A planned task that was still open when the workday ended."),
                  _t("Drop candidate", "An open task with no due date that nobody has touched for 30 days.")],
        "diagram": _d("The review only reports what was recorded.", [
            _n("rec", "Tasks and focus sessions", 0, 0, "store", "written during the week"),
            _n("calc", "Review data", 1, 0, "harness", "computed, not estimated"),
            _n("say", "The assistant's review", 2, 0, "model", "words over the numbers")],
            [_e("rec", "calc", "read"), _e("calc", "say", "numbers")]),
        "try": [_s("Read the panels on a fresh store.", "They say plainly that there is nothing to review yet."),
                _s("In chapter 12, press \"Simulate five working days\", then return here.",
                   "The panels fill with what that week recorded."),
                _s("Press \"Ask the assistant for the review\".",
                   "The text quotes the same numbers the panels show.")],
        "takeaways": ["A review is only as good as the records behind it.",
                      "Numbers come from the harness. The model adds the wording.",
                      "An honest empty state is better than an invented summary."],
        "notebook": [12],
    },
    "system_one": {
        "what": "Some decisions have a closed set of answers: is this email an attack, which procedure "
                "applies. A small second model answers each with a probability. The harness turns the "
                "number into a decision.",
        "why": "PPA screens every message from a stranger. Asking the large model for each one is slow "
               "and costly. A small model that only decides is fast, and it writes no text.",
        "terms": [_t("System One", "A small model that answers a closed question with a probability."),
                  _t("Threshold", "The number, owned by the harness, above which a probability counts as yes."),
                  _t("Fallback", "The written rule the harness uses when System One is off.")],
        "diagram": _d("One model decides. The other reasons.", [
            _n("q", "A closed question", 0, 0, "harness", "attack or not?"),
            _n("one", "System One", 1, 0, "model", "a probability"),
            _n("rule", "Rule, when it is off", 1, 1, "harness", "the fallback"),
            _n("cut", "Harness threshold", 2, 0, "gate"),
            _n("two", "Claude reasons", 3, 0, "model", "with what was let through")],
            [_e("q", "one", "ask"), _e("q", "rule", "no key"), _e("one", "cut", "number"),
             _e("rule", "cut", "yes or no"), _e("cut", "two", "decision")]),
        "try": [_s("Read the status at the top.", "With no key it says System One is off and rules decide."),
                _s("Press \"Screen the inbox\" in Lab 1.",
                   "The tripwire's answer is shown for each thread. System One's column is empty when it is off."),
                _s("Press \"Decide\" in Lab 2.", "The rule's choice of procedure is shown beside System One's.")],
        "takeaways": ["Decide with a small model, reason with a large one.",
                      "The harness owns the threshold, so a decision can be explained and changed.",
                      "Every decision has a fallback, so the assistant works with System One off."],
        "notebook": [7],
    },
    "context_cost": {
        "what": "A ledger of what each turn put in the prompt and what each model call cost. The prompt "
                "is shown layer by layer. Each call is split into fresh, written and read tokens.",
        "why": "PPA sends the same rules and tools on every turn of a working day. Without a ledger "
               "nobody can say what a day cost, or whether the prompt cache is working.",
        "terms": [_t("Context layer", "One part of the prompt with one source: the system prompt, the tool "
                                      "schemas, memory, skills, the request."),
                  _t("Prompt caching", "The model service keeps the start of a prompt it has seen, and "
                                       "charges much less to read it again."),
                  _t("Fresh token", "An input token that was not read from the cache and is billed at the "
                                    "full price.")],
        "diagram": _d("How an input token is billed.", [
            _n("prompt", "Prompt for one call", 0, 0, "harness", "prefix, then what is new"),
            _n("seen", "Start already cached?", 1, 0, "gate"),
            _n("read", "Cache read", 2, 0, "store", "a twentieth of the price"),
            _n("write", "Cache write", 2, 1, "store", "a little more than fresh"),
            _n("fresh", "Fresh", 2, 2, "model", "the full price"),
            _n("ledger", "One row in the ledger", 3, 0, "store", "tokens, seconds, cost")],
            [_e("prompt", "seen", "send"), _e("seen", "read", "yes"), _e("seen", "write", "new prefix"),
             _e("seen", "fresh", "after the breakpoint"), _e("read", "ledger", "count")]),
        "try": [_s("Run a request on the Assistant page, then return here.",
                   "A new bar appears, one segment for each layer of that turn's prompt."),
                _s("Press \"Show as a table\" under the chart.", "The same layer sizes are listed as numbers."),
                _s("Select a turn in \"Turns\".",
                   "Its model calls are listed with fresh, written and read tokens and their cost."),
                _s("Read the note above the chart when the responder is scripted.",
                   "It says no model was called, so tokens and cost are zero. Layer sizes are still real.")],
        "takeaways": ["Most of a prompt is the same on every turn. That is what makes caching pay.",
                      "Fresh tokens are input tokens minus cache reads minus cache writes.",
                      "A prompt that changes in the middle loses its cache. Add to the end only.",
                      "Layer sizes are approximate: characters divided by four."],
        "notebook": [9, 11],
    },
    "learning": {
        "what": "The assistant keeps a record of every turn, called a trajectory. When it handles the "
                "same kind of request the same way more than once with no skill, that workflow can "
                "become a new skill. A gate decides whether the skill goes live.",
        "why": "PPA meets the owner's habits one request at a time. A procedure learned from approved "
               "turns saves working it out again. A procedure that goes live untested could send mail "
               "wrongly, so every candidate must pass the same checks first.",
        "terms": [_t("Trajectory", "The record of one turn: the request, the tools that ran in order, and "
                                   "how it ended."),
                  _t("Promotion gate", "A fixed list of checks a candidate skill must pass before it is "
                                       "offered to the model."),
                  _t("Replay", "A test run of one request with a candidate live. Every write is declined, "
                               "so nothing is sent.")],
        "diagram": _d("From repeated turns to a live skill, and back.", [
            _n("turns", "Trajectories", 0, 0, "store", "one row for each turn"),
            _n("found", "Repeated workflow", 1, 0, "harness", "same tools, no skill, twice"),
            _n("fix", "A correction", 1, 1, "person", "words on a declined action"),
            _n("cand", "Candidate version", 2, 0, "store", "stored, not offered"),
            _n("gate", "Promotion gate", 3, 0, "gate", "five checks"),
            _n("live", "Live skill", 4, 0, "harness", "the pointer moves"),
            _n("back", "Roll back", 5, 0, "gate", "the pointer moves back")],
            [_e("turns", "found", "read"), _e("found", "cand", "draft"), _e("fix", "cand", "refine"),
             _e("cand", "gate", "test"), _e("gate", "live", "pass"), _e("live", "back", "any stored version")]),
        "try": [_s("Press \"Load a sample week\".",
                   "Five scripted turns appear in the trajectory table, each with an outcome."),
                _s("Under \"Candidates\", press \"Draft a skill\".",
                   "A version 1 appears in the history, marked CANDIDATE. It is not offered to the model."),
                _s("Press \"Run the gate\".", "Five checks fill in one by one, each with a reason."),
                _s("Press \"Promote\", then route the correction under \"Where does a correction belong?\".",
                   "The skill goes live. The correction is routed to one of three destinations.")],
        "takeaways": ["Evidence comes only from live turns that were approved or only read.",
                      "The gate is written before any candidate exists, and is the same for all of them.",
                      "A replay never writes: every write waits at the gate and is declined.",
                      "Nothing is deleted. Rolling back moves a pointer to an older version."],
        "notebook": [13],
    },
    "scorecard": {
        "what": "A frozen list of checks, each with a threshold and the evidence it reads. Together they "
                "give one verdict: READY or BLOCKED, with the failing checks named.",
        "why": "PPA acts in the owner's name. \"It seemed fine when I tried it\" is not enough to let it "
               "run. The scorecard states what must be true, and reads it from the records.",
        "terms": [_t("Release gate", "The rule that the assistant is ready only when every blocking check passes."),
                  _t("Evidence", "Rows the harness wrote while working: the action log, tasks, runs and "
                                 "model calls."),
                  _t("Informational check", "A figure that is reported and watched, and never blocks.")],
        "diagram": _d("Records in, a verdict out.", [
            _n("ev", "Evidence", 0, 0, "store", "audit, tasks, runs, model calls"),
            _n("checks", "Frozen checks", 1, 0, "harness", "each with a threshold"),
            _n("ready", "READY", 2, 0, "store", "every blocking check passes"),
            _n("blocked", "BLOCKED", 2, 1, "gate", "failing checks named")],
            [_e("ev", "checks", "read"), _e("checks", "ready", "all pass"),
             _e("checks", "blocked", "one fails")]),
        "try": [_s("Read the verdict on a fresh store.", "It is READY: nothing has broken a rule yet."),
                _s("Run a few requests on the Assistant page and press \"Compute again\".",
                   "The values change. The audit check counts the effects of those turns."),
                _s("Read the three informational rows.",
                   "With the scripted responder they say no model was called.")],
        "takeaways": ["A check names its evidence, so anyone can verify it.",
                      "Thresholds are fixed before the run, not adjusted after it.",
                      "Safety checks block. Cost and time are reported."],
        "notebook": [11, 14],
    },
}


def frame(identity: str) -> dict[str, Any] | None:
    """One chapter's frame, with the titles of the notebook Parts it matches."""
    found = CHAPTERS.get(identity)
    if found is None:
        return None
    return {**found, "id": identity,
            "notebook": [{"part": number, "title": PARTS[number]} for number in found["notebook"]]}


def everything() -> dict[str, Any]:
    return {"notebook": NOTEBOOK, "parts": PARTS, "primer": PRIMER,
            "chapters": {identity: frame(identity) for identity in CHAPTERS}}
