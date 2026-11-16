"""The reference architecture as one data structure.

Lanes, components, edges, request paths and the implementation ledger live
here and nowhere else. The diagram, the side panel and the stepper in the
browser are drawn from this structure. Every status is the result of a check
made when the page asks, never a stored colour.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from collections.abc import Callable
from importlib import metadata
from typing import Any

import policy

from backend.config import settings
from backend.core import (approval, clock, explorer, governed, llm_client, oracle_store, oracle_window,
                          scorecard, scripted, store, system_one, tools, tracing, websearch, world)
from backend.core.agent import NODES, agent
from backend.core.events import bus
from backend.core.memory import memory_provider
from backend.core.scheduler import scheduler
from backend.core.workspace import ALLOWLIST, SYSTEMS, TIER_RULES, WorkspaceError, workspace

STATUSES: dict[str, dict[str, str]] = {
    "connected": {"label": "Connected", "meaning": "Checked just now and working."},
    "configured": {"label": "Configured", "meaning": "Set up. It is exercised on its next use."},
    "fallback": {"label": "Fallback", "meaning": "A stand-in is doing this job."},
    "off": {"label": "Off", "meaning": "Switched off, or not in use at the moment."},
    "not_configured": {"label": "Not configured", "meaning": "Needs a key or a connection."},
    "failing": {"label": "Failing", "meaning": "The last check failed."},
}

LANES: list[dict[str, str]] = [
    {"id": "people", "title": "People and time",
     "about": "What starts a turn: the owner at the page, a schedule, an event or a timer."},
    {"id": "loop", "title": "Control loop",
     "about": "LangGraph StateGraph, checkpointed in the local store after every step."},
    {"id": "services", "title": "Harness services",
     "about": "Python code the loop calls. The notebook keeps several of these inside the database."},
    {"id": "models", "title": "Models",
     "about": "What decides, what reasons, and what ranks memories and skills."},
    {"id": "db", "title": "Stores",
     "about": "What the harness owns and keeps, in the appbook's local store. The notebook's store, "
              "Oracle AI Database 26ai, can be read here and is never written."},
    {"id": "mcp", "title": "Connectors",
     "about": "MCP: a gateway process with three servers, the harness allowlist and safe mode."},
    {"id": "world", "title": "Systems of record",
     "about": "Where mail, calendar and notes really live. The practice workspace is the default; "
              "your own accounts are optional."},
    {"id": "extra", "title": "Optional services",
     "about": "Each one is switched on by the environment and off by its absence."},
]

LOOP_FILE = "backend/core/agent.py"
WORKSPACE_FILES = ["part_3/_shared/mcp/workspace_mcp_server.py", "part_3/_shared/workspace/gateway.py"]


def _part(identity: str, lane: str, title: str, label: str, what: str, why: str, technology: str, *,
          files: list[str], tables: list[str] | None = None, endpoints: list[str] | None = None,
          tool_names: list[str] | None = None, chapter: str | None = None, tier: str | None = None,
          build: str = "built") -> dict[str, Any]:
    return {"id": identity, "lane": lane, "title": title, "label": label, "what": what, "why": why,
            "technology": technology, "build": build, "tier": tier,
            "artefacts": {"tables": tables or [], "endpoints": endpoints or [], "files": files,
                          "tools": tool_names or []},
            "jump": {"chapter": chapter, "table": (tables or [None])[0]}}


def _table(identity: str, group: str, title: str, tables: list[str], what: str, why: str, chapter: str,
           technology: str = "A table in the local store") -> dict[str, Any]:
    """A table, or a few that belong together. ``group`` is the card it sits on in the notebook's diagram."""
    part = _part(identity, "db", title, tables[0], what, why, technology,
                 files=["backend/core/store.py"], tables=tables, chapter=chapter)
    return {**part, "group": group}


def _connector(identity: str, system: str, title: str, what: str, source: str) -> dict[str, Any]:
    part = _part(identity, "world", title, f"your own {system}: optional", what,
                 "The assistant is only useful on the owner's own mail, calendar and notes. The "
                 "connector is the one place that speaks the provider's protocol.",
                 "Provider code in the shared workspace package, run by the gateway",
                 files=[source], endpoints=["/admin/providers", "/admin/connect", "/admin/disconnect"],
                 chapter="systems_of_record")
    return {**part, "system": system}


COMPONENTS: list[dict[str, Any]] = [
    # ── People and surfaces ──────────────────────────────────────────────────
    _part("owner", "people", "The owner", "the person the assistant works for",
          "The person whose mail, calendar, notes and tasks the assistant works on. In the practice "
          "workspace this is the owner of a public mailbox; with real accounts it is you.",
          "Every outward action needs a person who can say no. The owner approves or rejects each "
          "gated action, and only the owner can switch safe mode off.",
          "Persona, working hours and contacts, read from the gateway at start-up",
          files=["backend/core/world.py"], endpoints=["/api/status", "/admin/world"],
          chapter="systems_of_record"),
    _part("ui", "people", "Appbook UI", "assistant, chapters, data explorer",
          "One page served by the backend: the Assistant workspace, the building-block chapters and "
          "the docked data explorer. It is plain JavaScript with no build step.",
          "The owner needs a surface to type requests, watch each step of a run and decide on gated "
          "actions. The chapters show the same state the assistant uses, not a copy of it.",
          "HTML, CSS and JavaScript served as static files. Fonts come from Google Fonts when the "
          "machine is online, and fall back to system fonts when it is not.",
          files=["frontend/index.html", "frontend/app.js", "frontend/assistant.js",
                 "frontend/architecture.js", "frontend/chapters.js", "frontend/chapters-runtime.js",
                 "frontend/explorer.js"],
          endpoints=["/", "/api/events"], chapter="assistant"),
    _part("api", "people", "HTTP API", "one router per chapter",
          "The FastAPI application: one router per chapter, plus the routes for status, the clock, "
          "notifications and the event stream.",
          "Chat, approvals and every chapter reach the harness through the same typed endpoints, "
          "so the page has no private path to state.",
          "FastAPI and uvicorn",
          files=["backend/main.py", "backend/routers/", "backend/schemas.py"],
          endpoints=["/api/status", "/api/assistant/turn", "/api/assistant/resume", "/api/architecture"],
          chapter="assistant"),

    _part("routines", "people", "Scheduled routines", "brief, wrap, weekly review",
          "Three schedules taken from the owner's working hours: a morning brief before the day "
          "starts, an end-of-day wrap when it ends and a weekly review on Friday afternoon. Each "
          "arms a job for its next occurrence.",
          "Proactive work has to pass the same gates as chat. A routine cannot send mail that a "
          "typed request could not.",
          "Python", files=["backend/core/scheduler.py", "backend/core/routines.py"],
          tables=["ppa_schedules"],
          endpoints=["/api/routines/status", "/api/routines/schedules/{name}",
                     "/api/routines/run/{kind}", "/api/routines/simulate_week"],
          chapter="routines"),
    _part("triggers", "people", "Event triggers", "a meeting soon, mail from a VIP",
          "Two conditions the harness checks by itself: a meeting that starts within 30 minutes, and "
          "new mail from a VIP. When one becomes true a job is armed once, recognised by a key, so "
          "the same meeting is never prepared twice.",
          "Some work should start because something happened, not because someone asked.",
          "Python", files=["backend/core/routines.py"], tables=["ppa_automation_queue", "ppa_meta"],
          endpoints=["/api/routines/triggers/evaluate", "/api/routines/automation"],
          chapter="routines"),
    _part("focus", "people", "Focus timers", "a Pomodoro that ends by itself",
          "Starts, stops and completes focus sessions. A session is a row tied to a task, with a "
          "one-shot job in the automation queue. Distractions are parked until the session ends.",
          "A timer kept in memory is lost on a restart. A timer kept as a row is not.",
          "Python", files=["backend/core/focus.py"], tables=["ppa_focus_sessions"],
          endpoints=["/api/focus_sessions/status", "/api/focus_sessions/start",
                     "/api/focus_sessions/stop"],
          tool_names=["pomodoro_start", "pomodoro_status", "pomodoro_stop"], chapter="focus_sessions"),

    # ── The loop ─────────────────────────────────────────────────────────────
    _part("assemble_context", "loop", "assemble_context", "builds the turn",
          "The first node of every run. It builds the first user message of the turn from the clock, "
          "standing memories, memories recalled for this request, the governed definitions and the "
          "skill manifests.",
          "The system prompt and the tool list are fixed for the life of a conversation, so "
          "everything that changes must travel in the turn. An append-only context keeps the prompt "
          "cache valid and lets the model keep its earlier reasoning.",
          "LangGraph node", files=[LOOP_FILE], endpoints=["/api/the_loop/context"], chapter="the_loop"),
    _part("call_model", "loop", "call_model", "asks the responder",
          "Sends the conversation to the responder and records the answer, the tool calls, the token "
          "counts and the stop reason.",
          "One node calls the model, so one node handles refusals, time-outs and the limit on model "
          "calls in a turn.",
          "LangGraph node", files=[LOOP_FILE, "backend/core/llm_client.py"],
          endpoints=["/api/assistant/turn"], chapter="the_loop"),
    _part("dispatch_tools", "loop", "dispatch_tools", "validates and runs",
          "Checks each tool call against its schema, runs the automatic tools, and sets gated calls "
          "aside for a decision.",
          "The model proposes and the harness decides what runs. A call that fails validation goes "
          "back to the model as an error it can read and correct.",
          "LangGraph node", files=[LOOP_FILE, "backend/core/tools.py"], chapter="the_loop"),
    _part("draft_effects", "loop", "draft_effects", "drafts gated actions",
          "Turns each gated call into a drafted action: a summary, the stated reason, a risk "
          "assessment and the exact payload. Nothing has been executed at this point.",
          "The owner must see exactly what would happen before it happens.",
          "LangGraph node", files=[LOOP_FILE, "backend/core/approval.py"], tables=["ppa_action_audit"],
          chapter="approvals"),
    _part("human_review", "loop", "human_review", "pauses for a decision",
          "Pauses the run with interrupt(). The state is saved in a checkpoint and the run waits for "
          "the owner's decision, across a restart if need be.",
          "Approval is a step of the loop, not a dialogue in the page. The decision resumes the same "
          "run with Command(resume=...).",
          "LangGraph interrupt() and Command(resume=...)", files=[LOOP_FILE],
          tables=["checkpoints"], endpoints=["/api/assistant/resume", "/api/approvals/{action_id}/decide"],
          chapter="approvals"),
    _part("apply_effects", "loop", "apply_effects", "executes what was approved",
          "Executes approved actions through the gateway and records what was really delivered. A "
          "rejected action goes back to the model as a declined tool result.",
          "Approved and delivered are different facts. Safe mode can hold an approved message, and "
          "the log has to say so.",
          "LangGraph node", files=[LOOP_FILE, "backend/core/approval.py"], tables=["ppa_action_audit"],
          chapter="approvals"),
    _part("persist", "loop", "persist", "stores the run",
          "Stores the run, its trace and the readable transcript, then ends the turn.",
          "Every run, typed or proactive, leaves a record that the chapters and the data explorer "
          "can show.",
          "LangGraph node", files=[LOOP_FILE], tables=["ppa_agent_runs", "ppa_thread_messages"],
          endpoints=["/api/the_loop/status", "/api/the_loop/trace/{run_id}"], chapter="the_loop"),

    # ── Services ─────────────────────────────────────────────────────────────
    _part("tools", "services", "Trusted tools", "typed schemas, effect tiers",
          "The tools the model can call. Each has a typed argument schema, and each tool that writes "
          "asks for a reason. A tier says whether a tool runs at once or waits for a decision.",
          "Tools are the only path from the model to an effect, so they are where limits are "
          "enforced.",
          "Pydantic models, offered to the model as JSON Schema",
          files=["backend/core/tools.py"], tables=["ppa_tool_registry"],
          endpoints=["/api/systems_of_record/status"], chapter="systems_of_record",
          tier="Each tool has a tier of its own: automatic, approval or conditional."),
    _part("approval_gate", "services", "Approval gate", "assess, record, execute",
          "Assesses each gated action for recipient risk, quarantined threads, calendar conflicts and "
          "shared pages, records it in the action log, and executes it only after the owner decides.",
          "Sending mail, creating or answering invitations and editing a shared page affect other "
          "people. Each needs a person's decision, one action at a time.",
          "Python", files=["backend/core/approval.py"], tables=["ppa_action_audit"],
          endpoints=["/api/approvals/status", "/api/approvals/{action_id}/decide",
                     "/api/approvals/{action_id}/undo"],
          chapter="approvals", tier="It handles every action in the approval tier, and a conditional action "
                                   "when the page it touches is shared."),
    _part("policy", "services", "Shared policy", "governed meaning",
          "One definition each for urgent, free, VIP and over-booked, and the rules for triage, task "
          "order, slipping and stale tasks. Every Part 2 build imports the same file.",
          "A word such as urgent has to mean the same thing in the brief, in triage and in the "
          "weekly review. The definitions live in code, not in a prompt.",
          "Python functions with no model call",
          files=["part_3/_shared/runtime/policy.py", "backend/core/governed.py"],
          endpoints=["/api/governed_meaning/status", "/api/governed_meaning/compare"],
          chapter="governed_meaning"),
    _part("untrusted", "services", "Untrusted-content wrapper", "and the injection tripwire",
          "Every email, page and web result that reaches the model is wrapped as delimited data. A "
          "tripwire, a set of text patterns, looks for instruction-like mail from unknown senders. A "
          "hit quarantines the thread, and its sender, subject and text are withheld from the model.",
          "Text from outside can contain instructions aimed at the assistant. The wrapper marks it "
          "as data, the tripwire catches crude attempts, and the approval gate stops what both miss.",
          "policy.wrap_untrusted and policy.detect_injection",
          files=["part_3/_shared/runtime/policy.py", "backend/core/inbox.py"],
          endpoints=["/api/approvals/wrap", "/api/inbox_triage/thread/{thread_id}"],
          chapter="inbox_triage", build="partial"),
    _part("triage", "services", "Inbox triage", "governed categories",
          "Reads recent threads through MCP, applies the shared policy and gives each thread a "
          "category: reply, task, delegate, archive, tracked or quarantine. A task links back to its "
          "thread.",
          "Triage turns mail into a short list of decisions, and makes sure one thread never "
          "produces two tasks.",
          "Python", files=["backend/core/inbox.py"],
          endpoints=["/api/inbox_triage/status", "/api/inbox_triage/extract"],
          tool_names=["triage_inbox"], chapter="inbox_triage"),
    _part("calendar", "services", "Calendar intelligence", "slots, load, blocks, prep",
          "Free slots, meeting load, broken meeting rules, time-blocking and meeting preparation, "
          "computed from events read through MCP and the owner's working hours.",
          "A plan has to respect real events and the owner's rules, not the model's guess at them.",
          "Python", files=["backend/core/calendar_intel.py"],
          endpoints=["/api/calendar_intel/status", "/api/calendar_intel/plan",
                     "/api/calendar_intel/prep/{event_id}"],
          tool_names=["day_overview", "free_slots", "week_load", "plan_time_blocks", "meeting_prep"],
          chapter="calendar_intel"),
    _part("skills", "services", "Skills", "progressive disclosure",
          "Written procedures, such as the morning brief and the weekly review. Every turn "
          "carries their one-line manifests; the model loads one full body with load_skill when it "
          "needs it.",
          "A procedure is long. Loading one on demand keeps every turn small.",
          "Markdown bodies in a registry table, ranked by keyword overlap",
          files=["backend/core/skills.py"], tables=["ppa_skill_registry"],
          endpoints=["/api/skills/status", "/api/skills/{name}"], tool_names=["load_skill"],
          chapter="skills", build="partial"),
    _part("memory_provider", "services", "Memory provider", "LocalMemoryProvider",
          "Long-term memory: preferences, people, commitments, facts and one episode for each "
          "workday, each with a time to live. Recall ranks memories by the words they share with "
          "the request.",
          "A preference stated on Monday has to hold on Friday, in a new conversation.",
          "A provider interface with one local implementation",
          files=["backend/core/memory.py"], tables=["ppa_memories"],
          endpoints=["/api/memory_layer/status", "/api/memory_layer/recall"],
          tool_names=["memory_write", "memory_search"], chapter="memory_layer", build="partial"),
    _part("scratch", "services", "Workday scratch pad", "ScratchFS",
          "Working files for one workday: quick captures, the day plan and notes. When the day ends, "
          "marked notes are promoted to tasks or memories once, recognised by a hash of their text.",
          "Most of what is written during a day should be forgotten. Promotion keeps the few things "
          "that should last.",
          "Python over three tables", files=["backend/core/scratchfs.py"],
          tables=["ppa_scratch_files", "ppa_agent_sessions", "ppa_memory_promotion_queue"],
          endpoints=["/api/memory_layer/capture", "/api/memory_layer/session/end"],
          tool_names=["capture_note", "scratch_write", "scratch_read", "scratch_list", "end_workday"],
          chapter="memory_layer"),
    _part("scheduler", "services", "Scheduler", "thread polling the queue",
          "A background thread that polls the automation queue, fires the jobs that are due and "
          "hands each to its handler on the server's event loop. It also checks the event triggers "
          "at a fixed interval.",
          "Timers and routines have to fire without a request from the page, and have to survive a "
          "restart.",
          "A Python thread; DBMS_SCHEDULER and a queue worker do this job in the notebook",
          files=["backend/core/scheduler.py"], tables=["ppa_automation_queue"],
          endpoints=["/api/routines/jobs", "/api/routines/automation"], chapter="routines",
          build="mirror"),
    _part("handler", "services", "Job handler", "runs a fired job",
          "Runs each job the scheduler fires. It completes a focus session, or asks the loop for a "
          "brief, a wrap, a review, a meeting preparation or an alert, and delivers the answer as a "
          "notification.",
          "Every request, typed or scheduled, enters through agent.run, so there is one set of "
          "gates. The summary of a timer is written by the scripted responder, so that it arrives "
          "on time.",
          "Python", files=["backend/core/routines.py", "backend/core/notifications.py"],
          tables=["ppa_notifications"], endpoints=["/api/notifications", "/api/routines/jobs/{job_id}/fire"],
          chapter="routines"),
    _part("review", "services", "Reviews", "weekly and end of day",
          "Planned against done, time by task, what keeps slipping and what to drop, computed from "
          "tasks and focus sessions over the last seven days on the harness clock.",
          "The numbers in a review must come from rows, so the model reports them and does not "
          "invent them.",
          "Python", files=["backend/core/review.py"],
          endpoints=["/api/weekly_review/status", "/api/weekly_review/run"],
          tool_names=["weekly_review_data", "end_of_day_data"], chapter="weekly_review"),
    _part("ledger", "services", "Context and cost ledger", "one row for each model call",
          "Records, for every model call, how many input tokens were fresh, written to the prompt "
          "cache or read from it, how many came out, how long it took and what it cost. It also "
          "sums the approximate size of each layer of the prompt.",
          "The same rules and tools are sent on every turn of a working day. Without a ledger "
          "nobody can say what the day cost or whether the prompt cache is working.",
          "Python over one table; prices are settings",
          files=["backend/core/ledger.py", "backend/routers/context_cost.py"], tables=["ppa_model_calls"],
          endpoints=["/api/context_cost/status", "/api/context_cost/turn/{turn_id}"],
          chapter="context_cost"),
    _part("trajectories", "services", "Trajectories", "the record of each turn",
          "Writes one row for each turn: the request, the tools bound, the size of each context "
          "layer, the tools that ran in order, the outcome and the owner's words on a decline. The "
          "row is opened when the turn starts and closed when it ends.",
          "A turn that pauses for approval may wait for days. Its record has to be in the store, "
          "and learning needs to know how each turn ended.",
          "Python over one table, called from the loop",
          files=["backend/core/trajectories.py", "backend/core/agent.py"], tables=["ppa_turns"],
          endpoints=["/api/learning/status", "/api/learning/trajectories/{turn_id}"],
          chapter="learning"),
    _part("learning", "services", "Learning from traces", "draft, gate, promote, roll back",
          "Finds workflows the assistant repeated with no skill, drafts a candidate skill from them, "
          "runs five checks on it and, when they pass, makes it live. It routes a correction to a "
          "procedure, to long-term memory or to nowhere, and can move a skill back to any version.",
          "A procedure learned from approved turns saves working it out again. One that goes live "
          "untested could act wrongly in the owner's name, so every candidate passes the same gate.",
          "Python; Claude writes candidates when it is available, a template otherwise",
          files=["backend/core/learning.py", "backend/core/skills.py", "backend/routers/learning.py"],
          tables=["ppa_skill_versions", "ppa_skill_log"],
          endpoints=["/api/learning/draft", "/api/learning/skills/{name}/{version}/gate",
                     "/api/learning/skills/{name}/{version}/promote", "/api/learning/skills/{name}/activate",
                     "/api/learning/correction/route", "/api/learning/sample_week"],
          chapter="learning"),
    _part("scorecard", "services", "Scorecard", "READY or BLOCKED",
          "A frozen list of checks, each with a threshold and the evidence it reads. It computes "
          "every check from the live state and gives one verdict.",
          "An assistant that acts in the owner's name needs a stated bar, read from records, before "
          "it is trusted to run.",
          "Python over the action log, tasks, runs and the ledger",
          files=["backend/core/scorecard.py", "backend/routers/scorecard.py"],
          endpoints=["/api/scorecard/status"], chapter="scorecard"),
    _part("clock", "services", "Harness clock", "practice, pinned or real",
          "The clock the harness plans by. The practice workspace pins it and replays the mailbox "
          "against it; with a real account the real clock applies. Focus timers always use the real "
          "clock.",
          "Urgent, free and stale all depend on what time it is. A pinned clock makes a "
          "demonstration repeatable.",
          "Python", files=["backend/core/clock.py"], tables=["ppa_meta"],
          endpoints=["/api/clock", "/api/clock/reset"], chapter="routines"),
    _part("events", "services", "Event bus", "one stream to the page",
          "An in-process bus. Run steps, timers, notifications, actions and table activity are "
          "published on it and reach the page over one Server-Sent Events stream.",
          "The page shows steps as they happen and timers as they fire, without asking again and "
          "again.",
          "sse-starlette", files=["backend/core/events.py", "backend/routers/harness.py"],
          endpoints=["/api/events"], chapter="routines"),

    # ── Models ───────────────────────────────────────────────────────────────
    _part("system_one", "models", "System One", "Jev decides, rules stand behind it",
          "System One is the fast kind of thinking: a small model that answers a typed question "
          "with a probability. It writes no text and takes no action. The appbook asks it whether "
          "a message is an attack and which evidence is worth reading before a meeting, and its "
          "chapter measures it on choosing procedures and tools. When it is off, rules make the "
          "same decisions: the pattern tripwire screens mail and evidence keeps the order in which "
          "it was found.",
          "These decisions are made on every turn. Made by rules they are free and immediate, and "
          "they are crude: the tripwire misses most attacks. Asked of System One they cost a "
          "third of a second and a fraction of a cent.",
          "Jev 1.13 from Typesafe, over HTTP. Python rules when it is off.",
          files=["backend/core/system_one.py", "part_3/_shared/runtime/policy.py", "backend/core/inbox.py",
                 "backend/core/calendar_intel.py"],
          tables=["ppa_decision_log"],
          endpoints=["/api/system_one/status", "/api/system_one/attack_lab", "/api/system_one/select_lab"],
          chapter="system_one", build="partial"),
    _part("claude", "models", "Claude Opus 5.5", "System Two: reasons",
          "The model that reads the context, reasons about the request and chooses tools. System "
          "Two is the slow, deliberate kind of thinking. It runs with adaptive thinking, automatic "
          "tool choice and a prompt cache breakpoint.",
          "Open-ended reasoning over mail, calendar and tasks is the part of the work that rules "
          "cannot do.",
          "ChatAnthropic from langchain-anthropic", files=["backend/core/llm_client.py"],
          endpoints=["/api/assistant/turn"], chapter="the_loop"),
    _part("scripted", "models", "Scripted responder", "deterministic stand-in",
          "A deterministic router that sits where the model sits. It recognises a fixed set of "
          "requests, calls the same tools and writes its answers from their results.",
          "The appbook has to run with no credentials, and the summary of a finished timer has to "
          "arrive on time. The scripted responder does both.",
          "Python, regular expressions", files=["backend/core/scripted.py"], chapter="the_loop"),
    _part("embedding", "models", "Embedding model", "none: keyword overlap",
          "There is no embedding model in the appbook. Memory recall and skill ranking compare the "
          "words in the request with the words in each memory or skill.",
          "Recall decides which memories reach the model. Keyword overlap is a stand-in: it misses "
          "a memory that says the same thing in other words.",
          "Keyword overlap in Python. In-database vector search belongs to the notebook.",
          files=["backend/core/memory.py", "backend/core/skills.py"], chapter="memory_layer",
          build="partial"),

    # ── State and memory ─────────────────────────────────────────────────────
    {**_part("database", "db", "Local store", "one file per owner",
          "All harness state for one owner is kept in one file on this machine, named by a hash of "
          "the owner's address. LangGraph checkpoints have a file of their own.",
          "A practice run must never mix with a real account, and a checkpoint write must never "
          "block a harness write.",
          "A file database from the Python standard library, in write-ahead-log mode",
          files=["backend/core/store.py", "backend/core/explorer.py"], tables=["ppa_meta"],
          endpoints=["/api/data_explorer/tables"], build="mirror"), "group": "The store"},
    {**_part("oracle", "db", "Oracle AI Database", "the notebook's store, read-only",
             "The database the custom-harness notebook runs on. The appbook does not store anything "
             "in it. The data explorer opens a read-only window on it, to show what the notebook's "
             "harness left there: its tables and governed views, LangGraph checkpoints, Oracle Agent "
             "Memory, the scheduler jobs and the embedding model.",
             "A learner who has run the notebook can see the same anatomy in both stores: the tables "
             "the appbook keeps in its local store, and the ones Oracle keeps, with vectors and an embedding "
             "model inside the database.",
             "Oracle AI Database 26ai, read through python-oracledb in thin mode",
             files=["backend/core/oracle_window.py", "backend/routers/oracle_window.py",
                    "frontend/oracle-explorer.js"],
             endpoints=["/api/oracle", "/api/oracle/objects/{name}"]), "group": "The notebook's store"},
    _table("t_tasks", "State of record", "Tasks", ["ppa_tasks"],
           "The running to-do list: title, priority, due date, estimate, source link and how often "
           "a task was carried over.",
           "Tasks have no other home. Mail, calendar and notes stay in their own systems; tasks are "
           "what the harness owns.", "assistant"),
    _table("t_focus", "State of record", "Focus sessions", ["ppa_focus_sessions"],
           "One row for each Pomodoro: the task, planned and actual minutes, and how it ended.",
           "The weekly review reports where time went. It can only report what was recorded.",
           "focus_sessions"),
    _table("t_contacts", "State of record", "Contacts", ["ppa_contacts"],
           "The people the owner writes to, with VIP flags derived from the mailbox by the gateway.",
           "Sender trust and recipient risk both start from who the owner already knows.",
           "governed_meaning"),
    _table("t_meta", "State of record", "Settings", ["ppa_meta"],
           "Small values: the clock pin, the trigger watermark and the automation switch.",
           "A switch that is a row keeps its position across a restart.", "routines"),
    _table("t_scratch", "Working memory", "Scratch files", ["ppa_scratch_files", "ppa_agent_sessions",
                                          "ppa_memory_promotion_queue"],
           "The files of each workday session, the sessions themselves, and the queue of notes "
           "staged for promotion.",
           "Working notes are kept apart from long-term memory until something decides they should "
           "last.", "memory_layer"),
    _table("t_memories", "Long-term and episodic memory", "Long-term memory", ["ppa_memories"],
           "Preferences, people, commitments, facts and episodes, each with a type, a hash of its "
           "text and an expiry date.",
           "Memory that never expires fills with things that stopped being true.", "memory_layer"),
    _table("t_skills", "Skills and tools", "Skill registry", ["ppa_skill_registry"],
           "The live skills, one row each, with a version pointer and a hash of the body.",
           "Only what is in this table is offered to the model.", "skills"),
    _table("t_skill_versions", "Skills and tools", "Skill versions", ["ppa_skill_versions", "ppa_skill_log"],
           "Every version of every skill, with its origin, its evidence and its gate result, and a "
           "log of every move of a live pointer.",
           "A version that is never edited or deleted can always be made live again.", "learning"),
    _table("t_tools", "Skills and tools", "Tool registry", ["ppa_tool_registry"],
           "Every tool, reachable or not, with its source, its tier and its schema.",
           "It is the written record of what the model can reach and what it cannot.",
           "systems_of_record"),
    _table("t_queue", "Time", "Automation queue", ["ppa_automation_queue"],
           "Every timer and scheduled job: its kind, when it fires and its state, from armed to "
           "delivered.",
           "A job that is a row can be re-armed after a restart and shown with a live countdown.",
           "routines"),
    _table("t_schedules", "Time", "Schedules", ["ppa_schedules"],
           "The routines, the days and the local time they run, and when each last fired.",
           "A schedule the owner can read and change is a schedule the owner can trust.", "routines"),
    _table("t_notifications", "Time", "Notifications", ["ppa_notifications"],
           "What timers and routines reported, with the job and the run that produced each.",
           "A notification that was missed in the browser can still be read later.", "routines"),
    _table("t_checkpoints", "Durable checkpoints", "Checkpoints", ["checkpoints", "writes"],
           "The state of the graph after every step, kept by LangGraph in a file of its own.",
           "A run that is waiting for a decision has to survive a restart.", "the_loop",
           "A LangGraph checkpoint saver on the local store; OracleSaver does this job in the "
           "notebook"),
    _table("t_audit", "Evidence", "Action log", ["ppa_action_audit"],
           "Every effect: the tool, the reason, the payload, the risk assessment, the decision and "
           "what was delivered.",
           "It answers three questions after the fact: what was done, why, and did it really reach "
           "anyone.", "approvals"),
    _table("t_turns", "Evidence", "Trajectories", ["ppa_turns"],
           "One row for each turn: what was asked, what ran in which order, and how it ended.",
           "It is the evidence that a workflow was repeated, and that the owner approved it.",
           "learning"),
    _table("t_model_calls", "Evidence", "Model calls", ["ppa_model_calls"],
           "One row for each model call: fresh, written and read tokens, output tokens, seconds and cost.",
           "Cost and cache use can be read after the fact, turn by turn.", "context_cost"),
    _table("t_runs", "Evidence", "Runs and transcripts", ["ppa_agent_runs", "ppa_thread_messages"],
           "One row for each run with its trace, and the readable transcript of each conversation.",
           "A trace shows which tools ran, in what order, with what result and at what cost.",
           "the_loop"),

    # ── Workspace gateway ────────────────────────────────────────────────────
    _part("allowlist", "mcp", "Allowlist and tiers", "the workspace adapter",
          "The only module that talks to the gateway. It holds the allowlist: the MCP tools the "
          "harness may call and the tier of each. A tool that is not on the list cannot be reached, "
          "whatever the model asks for.",
          "The three MCP servers offer more tools than an assistant should use. The allowlist is the "
          "harness's own decision about which of them exist.",
          "langchain-mcp-adapters over streamable HTTP, with a 20-second read cache",
          files=["backend/core/workspace.py"],
          endpoints=["/api/systems_of_record/status", "/api/systems_of_record/attempt"],
          chapter="systems_of_record",
          tier="It gives each MCP tool a tier. A tool it leaves out is never exposed."),
    _part("gateway", "mcp", "Workspace gateway", "a separate process",
          "A process the appbook starts and stops. It holds the connections to mail, calendar and "
          "notes, serves three MCP servers and offers an operator API over plain HTTP.",
          "Credentials and provider code stay out of the harness. The model can reach a provider "
          "only through an MCP tool that the allowlist permits; it cannot reach the operator API "
          "at all.",
          "Starlette and the MCP Python SDK", files=WORKSPACE_FILES,
          endpoints=["/health", "/admin/world", "/admin/providers", "/admin/connect",
                     "/admin/disconnect", "/admin/clock", "/admin/reset"],
          chapter="systems_of_record"),
    *[_part(f"mcp_{name}", "mcp", f"{name.capitalize()} MCP server", f"/{name}/mcp",
            f"One of the three MCP servers. It offers the {name} tools of whichever provider is "
            "connected, under the same neutral names.",
            "Neutral tool names let the harness, its allowlist and its tests stay the same when the "
            "provider changes.",
            "MCP over streamable HTTP with a bearer token", files=WORKSPACE_FILES,
            endpoints=[f"/{name}/mcp"], chapter="systems_of_record",
            tier="Set by the harness allowlist, tool by tool.")
      for name in SYSTEMS],
    _part("safe_mode", "mcp", "Safe mode", "held by the gateway",
          "A switch that is on by default. With a real account, an approved message to anyone but "
          "the owner is held as a draft, and an approved event is created without other attendees.",
          "Approval answers whether an action should happen. Safe mode answers whether it may reach "
          "other people yet.",
          "A rule inside the gateway, so no harness code can skip it", files=WORKSPACE_FILES,
          endpoints=["/api/connections/safe_mode", "/admin/safe_mode"], chapter="systems_of_record"),
    _part("effects", "mcp", "Effect log", "what reached the provider",
          "The gateway's own record of every write it carried out or held: drafts, sent mail, "
          "created events and page edits. In the practice workspace it is kept in memory and is "
          "empty again after the gateway restarts.",
          "The action log says what was approved. The effect log says what reached the provider. "
          "Reading both shows approved against delivered.",
          "A list inside the gateway process", files=WORKSPACE_FILES,
          endpoints=["/admin/effects", "/api/systems_of_record/effects", "/admin/overlay.ics"],
          chapter="approvals"),

    # ── Providers ────────────────────────────────────────────────────────────
    _part("practice", "world", "Practice workspace", "the default: no sign-in",
          "A mailbox, a calendar and notes built from public datasets, with real attack emails "
          "placed in the inbox. It is the default, needs no credentials and changes nothing outside "
          "this machine.",
          "Learners need real mail to practise on before they connect their own. Real attacks show "
          "what the tripwire catches and what it misses.",
          "A compressed slice of public datasets, loaded by the gateway",
          files=["part_3/_shared/data/practice_slice.json.gz", "part_3/_shared/workspace/practice.py",
                 "part_3/_shared/data/build_practice_slice.py"],
          endpoints=["/admin/world", "/admin/inbox"], chapter="systems_of_record"),
    _connector("imap", "mail", "IMAP and SMTP mail",
               "Connects a real mailbox with an app password. The mailbox is opened read-only, and a "
               "message is sent only after the owner approves it.",
               "part_3/_shared/workspace/imap_mail.py"),
    _connector("google", "calendar", "Google Calendar",
               "Reads and writes a real Google calendar after the owner gives consent in the "
               "browser. An event is written only after the owner approves it.",
               "part_3/_shared/workspace/calendars.py"),
    _connector("ics", "calendar", "ICS calendar",
               "Reads a real calendar from its secret iCal address. It cannot write, so blocks the "
               "assistant creates stay in a local overlay that the owner can import.",
               "part_3/_shared/workspace/calendars.py"),
    _connector("notion", "notes", "Notion",
               "Reads and writes the Notion pages that the owner shared with the integration, and no "
               "others.",
               "part_3/_shared/workspace/notes.py"),
    _connector("folder", "notes", "Folder of notes",
               "Reads and writes Markdown files in one folder on this machine, for owners who do not "
               "use Notion.",
               "part_3/_shared/workspace/notes.py"),

    # ── Optional services ────────────────────────────────────────────────────
    _part("tavily", "extra", "Tavily", "web search",
          "The web_search tool. Results are text from outside, so they are wrapped as untrusted data "
          "before the model sees them. Without a key the tool answers that it is not configured.",
          "Some questions need evidence that is newer than the model and is not in the mailbox.",
          "tavily-python", files=["backend/core/websearch.py"], tool_names=["web_search"],
          chapter="systems_of_record"),
    _part("langsmith", "extra", "LangSmith", "traces of every step",
          "LangChain and LangGraph send a trace of every graph step, model call and tool result to "
          "LangSmith when the environment sets LANGSMITH_TRACING to true and a key is present. No "
          "appbook code starts, stops or changes that; the appbook only reports it.",
          "A trace shows what the model was sent and what it returned. It also means that the text "
          "the assistant reads, mail included, leaves this machine.",
          "langsmith, switched by the environment", files=["backend/core/tracing.py"],
          chapter="systems_of_record"),
]

# (from, to, what travels, part of the main flow)
EDGES: list[tuple[str, str, str, bool]] = [
    ("owner", "ui", "types a request, decides on actions", True),
    ("ui", "owner", "answers, approval cards, toasts", False),
    ("ui", "api", "HTTP and JSON", True),
    ("api", "assemble_context", "agent.run starts a run", True),
    ("api", "human_review", "the decision resumes the run", False),
    ("events", "ui", "Server-Sent Events", True),
    ("api", "oracle", "read-only queries for the data explorer", False),
    ("assemble_context", "call_model", "the turn", True),
    ("call_model", "dispatch_tools", "tool calls", True),
    ("dispatch_tools", "call_model", "tool results", False),
    ("dispatch_tools", "draft_effects", "gated calls", True),
    ("draft_effects", "human_review", "drafted actions", True),
    ("human_review", "apply_effects", "decisions", True),
    ("apply_effects", "call_model", "outcomes, declined ones included", False),
    ("call_model", "persist", "the answer", True),
    ("assemble_context", "clock", "the time", False),
    ("assemble_context", "memory_provider", "standing and recalled memories", False),
    ("assemble_context", "skills", "manifests", False),
    ("assemble_context", "policy", "governed definitions", False),
    ("call_model", "claude", "conversation and tools", True),
    ("call_model", "scripted", "conversation", False),
    ("call_model", "langsmith", "traces, when switched on", False),
    ("dispatch_tools", "tools", "validate and run", True),
    ("draft_effects", "approval_gate", "assess and record", False),
    ("human_review", "t_checkpoints", "the paused state", False),
    ("human_review", "events", "approval card", False),
    ("apply_effects", "approval_gate", "execute and record", False),
    ("approval_gate", "allowlist", "approved writes", False),
    ("approval_gate", "policy", "recipient risk", False),
    ("approval_gate", "t_audit", "drafted, decided, delivered", False),
    ("persist", "t_runs", "run, trace, transcript", False),
    ("persist", "t_checkpoints", "final state", False),
    ("persist", "events", "answer and trace", False),
    ("tools", "allowlist", "MCP reads and drafts", True),
    ("tools", "triage", "triage_inbox", False),
    ("tools", "calendar", "calendar tools", False),
    ("tools", "focus", "pomodoro tools", False),
    ("tools", "scratch", "capture and scratch tools", False),
    ("tools", "memory_provider", "memory tools", False),
    ("tools", "skills", "load_skill", False),
    ("tools", "review", "review tools", False),
    ("tools", "tavily", "web_search", False),
    ("tools", "t_tasks", "task tools", False),
    ("tools", "t_tools", "registry of tools and tiers", False),
    ("tools", "t_audit", "automatic effects", False),
    ("triage", "allowlist", "reads threads", False),
    ("triage", "policy", "triage signals", False),
    ("triage", "untrusted", "wrap or withhold", False),
    ("triage", "t_contacts", "sender trust", False),
    ("triage", "t_tasks", "tracked threads", False),
    ("untrusted", "policy", "patterns and wrapper", False),
    ("calendar", "allowlist", "reads events and pages", False),
    ("calendar", "policy", "free, over-booked, meeting rules", False),
    ("calendar", "scratch", "writes the day plan", False),
    ("calendar", "t_tasks", "planned tasks", False),
    ("memory_provider", "t_memories", "memories", False),
    ("memory_provider", "embedding", "ranks by keyword overlap", False),
    ("skills", "t_skills", "registry", False),
    ("call_model", "ledger", "tokens, seconds, cost", False),
    ("ledger", "t_model_calls", "one row for each call", False),
    ("assemble_context", "trajectories", "the size of each layer", False),
    ("persist", "trajectories", "tools that ran, outcome", False),
    ("trajectories", "t_turns", "one row for each turn", False),
    ("learning", "t_turns", "reads repeated workflows", False),
    ("learning", "t_skill_versions", "candidates and gate results", False),
    ("learning", "t_skills", "moves the live pointer", False),
    ("api", "learning", "draft, gate, promote, roll back", False),
    ("api", "scorecard", "compute the verdict", False),
    ("scorecard", "t_audit", "reads decisions", False),
    ("scorecard", "t_model_calls", "reads cost and cache use", False),
    ("skills", "embedding", "ranks by keyword overlap", False),
    ("scratch", "t_scratch", "files and promotion queue", False),
    ("scratch", "t_tasks", "promoted notes", False),
    ("scratch", "memory_provider", "promoted notes and the day's episode", False),
    ("focus", "t_focus", "session row", False),
    ("focus", "t_queue", "arms a one-shot job", False),
    ("focus", "scratch", "parked distractions", False),
    ("scheduler", "t_queue", "polls for due jobs", False),
    ("scheduler", "triggers", "checks at a fixed interval", False),
    ("scheduler", "handler", "hands over a fired job", False),
    ("scheduler", "t_meta", "automation switch", False),
    ("routines", "t_schedules", "days and times", False),
    ("routines", "t_queue", "arms the next occurrence", False),
    ("triggers", "calendar", "is a meeting about to start?", False),
    ("triggers", "allowlist", "is there new mail from a VIP?", False),
    ("triggers", "t_contacts", "who is a VIP", False),
    ("triggers", "t_meta", "watermark", False),
    ("triggers", "t_queue", "arms a job once", False),
    ("handler", "focus", "completes the session", False),
    ("handler", "assemble_context", "agent.run, proactive", True),
    ("handler", "t_notifications", "notification", False),
    ("handler", "events", "notification", False),
    ("handler", "scratch", "ends the workday after the wrap", False),
    ("untrusted", "system_one", "attack or not", False),
    ("assemble_context", "system_one", "which procedure, which tools", False),
    ("calendar", "system_one", "which evidence", False),
    ("review", "t_tasks", "planned and done", False),
    ("review", "t_focus", "time by task", False),
    ("clock", "t_meta", "clock pin", False),
    ("clock", "gateway", "practice clock", False),
    ("allowlist", "gateway", "MCP over streamable HTTP", True),
    ("gateway", "t_contacts", "contacts at start-up", False),
    ("gateway", "owner", "persona at start-up", False),
    ("gateway", "safe_mode", "checks each write", False),
    ("gateway", "effects", "records each write", False),
    *[("gateway", f"mcp_{name}", "serves", True) for name in SYSTEMS],
    ("mcp_mail", "practice", "practice mail", True),
    ("mcp_mail", "imap", "real mail", False),
    ("mcp_calendar", "practice", "practice calendar", False),
    ("mcp_calendar", "google", "real calendar", False),
    ("mcp_calendar", "ics", "real calendar, read-only", False),
    ("mcp_notes", "practice", "practice notes", False),
    ("mcp_notes", "notion", "real notes", False),
    ("mcp_notes", "folder", "real notes", False),
]


def _step(title: str, text: str, parts: list[str], edges: list[tuple[str, str]]) -> dict[str, Any]:
    return {"title": title, "text": text, "components": parts, "edges": [list(edge) for edge in edges]}


PATHS: list[dict[str, Any]] = [
    {"id": "brief", "title": "A morning brief", "kind": "read-only",
     "about": "A request that only reads. No gated tool is called, so the run never pauses.",
     "steps": [
         _step("The owner asks", "The owner types a request for a morning brief in the Assistant. The "
               "page posts it to the API.", ["owner", "ui", "api"], [("owner", "ui"), ("ui", "api")]),
         _step("A run starts", "The API calls agent.run, the one entry point for typed and proactive "
               "requests. The graph begins at assemble_context.", ["api", "assemble_context"],
               [("api", "assemble_context")]),
         _step("The turn is assembled", "The node gathers the time, the standing memories, the "
               "memories recalled for this request, the governed definitions and the skill manifests, "
               "and puts them in the first message of the turn.",
               ["assemble_context", "clock", "memory_provider", "t_memories", "embedding", "skills",
                "t_skills", "policy"],
               [("assemble_context", "clock"), ("assemble_context", "memory_provider"),
                ("memory_provider", "t_memories"), ("memory_provider", "embedding"),
                ("assemble_context", "skills"), ("skills", "t_skills"),
                ("assemble_context", "policy")]),
         _step("The responder is asked", "call_model sends the conversation to Claude when a key is "
               "configured, and to the scripted responder when it is not. The answer is a list of "
               "tool calls.", ["assemble_context", "call_model", "claude", "scripted"],
               [("assemble_context", "call_model"), ("call_model", "claude"),
                ("call_model", "scripted")]),
         _step("Tools are checked and run", "dispatch_tools checks each call against its schema. "
               "These are automatic tools, so they run at once: the skill is loaded, the inbox is "
               "triaged, the day is read and the tasks are listed.",
               ["call_model", "dispatch_tools", "tools", "skills", "triage", "calendar", "t_tasks"],
               [("call_model", "dispatch_tools"), ("dispatch_tools", "tools"), ("tools", "skills"),
                ("tools", "triage"), ("tools", "calendar"), ("tools", "t_tasks")]),
         _step("Mail and events are read", "Triage and the calendar read through the allowlist, the "
               "gateway and its MCP servers. Nothing they read is copied into the database.",
               ["triage", "calendar", "allowlist", "gateway", "mcp_mail", "mcp_calendar", "practice"],
               [("triage", "allowlist"), ("calendar", "allowlist"), ("allowlist", "gateway"),
                ("gateway", "mcp_mail"), ("gateway", "mcp_calendar"), ("mcp_mail", "practice"),
                ("mcp_calendar", "practice")]),
         _step("Outside text becomes data", "Each thread is classified by the shared policy. Mail text "
               "is wrapped as untrusted data before it is returned, and a quarantined thread is "
               "returned without its text.", ["triage", "policy", "untrusted", "t_contacts"],
               [("triage", "policy"), ("triage", "untrusted"), ("untrusted", "policy"),
                ("triage", "t_contacts")]),
         _step("The answer is written", "The tool results go back to the responder, which writes the "
               "brief. No gated tool was called, so the run did not pause.",
               ["dispatch_tools", "call_model", "claude", "scripted"],
               [("dispatch_tools", "call_model"), ("call_model", "claude"),
                ("call_model", "scripted")]),
         _step("The run is stored", "persist stores the run, its trace and the transcript. The answer "
               "reaches the page over the event stream, with every step it took.",
               ["call_model", "persist", "t_runs", "t_checkpoints", "events", "ui", "owner"],
               [("call_model", "persist"), ("persist", "t_runs"), ("persist", "t_checkpoints"),
                ("persist", "events"), ("events", "ui"), ("ui", "owner")]),
     ]},
    {"id": "approval", "title": "A write that waits for approval", "kind": "gated write",
     "about": "A calendar event affects other people, so the run pauses until the owner decides.",
     "steps": [
         _step("The owner asks", "The owner asks for the top tasks to be placed in today's calendar. A "
               "run starts and the turn is assembled as before.",
               ["owner", "ui", "api", "assemble_context", "call_model"],
               [("owner", "ui"), ("ui", "api"), ("api", "assemble_context"),
                ("assemble_context", "call_model")]),
         _step("The plan is read", "The responder reads the tasks and the free slots with automatic "
               "tools. Free has one governed definition, taken from the shared policy.",
               ["call_model", "claude", "scripted", "dispatch_tools", "tools", "calendar", "policy",
                "t_tasks"],
               [("call_model", "claude"), ("call_model", "scripted"), ("call_model", "dispatch_tools"),
                ("dispatch_tools", "tools"), ("tools", "calendar"), ("calendar", "policy"),
                ("tools", "t_tasks")]),
         _step("A gated tool is called", "The responder calls calendar_create_event. The tool is in "
               "the approval tier, so dispatch_tools does not run it and passes it to draft_effects.",
               ["call_model", "dispatch_tools", "draft_effects"],
               [("call_model", "dispatch_tools"), ("dispatch_tools", "draft_effects")]),
         _step("The action is drafted", "The approval gate checks the event for conflicts, working "
               "hours and recipients, and writes it to the action log in the state DRAFTED. Nothing "
               "has reached the calendar.", ["draft_effects", "approval_gate", "policy", "t_audit"],
               [("draft_effects", "approval_gate"), ("approval_gate", "policy"),
                ("approval_gate", "t_audit")]),
         _step("The run pauses", "human_review calls interrupt(). The state of the run is saved in a "
               "checkpoint, and the page shows an approval card.",
               ["draft_effects", "human_review", "t_checkpoints", "events", "ui", "owner"],
               [("draft_effects", "human_review"), ("human_review", "t_checkpoints"),
                ("human_review", "events"), ("events", "ui"), ("ui", "owner")]),
         _step("The owner decides", "The owner approves or rejects each action. The decision resumes "
               "the same run from its checkpoint with Command(resume=...), also after a restart.",
               ["owner", "ui", "api", "human_review", "t_checkpoints"],
               [("owner", "ui"), ("ui", "api"), ("api", "human_review")]),
         _step("Approved actions are executed", "apply_effects sends each approved action through the "
               "allowlist to the gateway. Safe mode decides what may reach other people, and both "
               "logs record the result.",
               ["human_review", "apply_effects", "approval_gate", "allowlist", "gateway", "safe_mode",
                "mcp_calendar", "effects", "t_audit"],
               [("human_review", "apply_effects"), ("apply_effects", "approval_gate"),
                ("approval_gate", "allowlist"), ("allowlist", "gateway"), ("gateway", "safe_mode"),
                ("gateway", "mcp_calendar"), ("gateway", "effects"), ("approval_gate", "t_audit")]),
         _step("The responder reads the outcome", "Each outcome returns as a tool result. A rejected "
               "action returns as declined, so the responder adapts its answer and does not try "
               "again. persist then stores the run.",
               ["apply_effects", "call_model", "claude", "scripted", "persist", "t_runs", "events",
                "ui"],
               [("apply_effects", "call_model"), ("call_model", "claude"), ("call_model", "scripted"),
                ("call_model", "persist"), ("persist", "t_runs"), ("persist", "events"),
                ("events", "ui")]),
     ]},
    {"id": "timer", "title": "A focus timer", "kind": "scheduled work",
     "about": "A Pomodoro becomes a job in the queue, fires on the real clock and reports back.",
     "steps": [
         _step("The owner asks", "The owner asks for a Pomodoro on a task. The responder calls "
               "pomodoro_start, an automatic tool: nobody else is affected.",
               ["owner", "ui", "api", "assemble_context", "call_model", "dispatch_tools", "tools"],
               [("owner", "ui"), ("ui", "api"), ("api", "assemble_context"),
                ("assemble_context", "call_model"), ("call_model", "dispatch_tools"),
                ("dispatch_tools", "tools")]),
         _step("A session and a job are written", "The focus runtime writes a session row tied to the "
               "task and arms a one-shot job in the automation queue. The job fires on the real "
               "clock.", ["tools", "focus", "t_focus", "t_queue"],
               [("tools", "focus"), ("focus", "t_focus"), ("focus", "t_queue")]),
         _step("The scheduler waits", "The scheduler thread polls the queue. The job is a row, so it "
               "is armed again if the appbook restarts before it fires.", ["scheduler", "t_queue"],
               [("scheduler", "t_queue")]),
         _step("The job fires", "When the time comes the scheduler marks the job FIRED and hands it "
               "to the job handler, which completes the session.",
               ["scheduler", "handler", "focus", "t_focus"],
               [("scheduler", "handler"), ("handler", "focus"), ("focus", "t_focus")]),
         _step("The summary is a run", "The handler enters the loop through agent.run, as a typed "
               "request does. The scripted responder writes the summary of a timer, so that it "
               "arrives on time.",
               ["handler", "assemble_context", "call_model", "scripted", "persist", "t_runs"],
               [("handler", "assemble_context"), ("assemble_context", "call_model"),
                ("call_model", "scripted"), ("call_model", "persist"), ("persist", "t_runs")]),
         _step("A notification is written", "The handler stores a notification and publishes it on "
               "the event bus. The job moves to DELIVERED.",
               ["handler", "t_notifications", "events", "t_queue"],
               [("handler", "t_notifications"), ("handler", "events")]),
         _step("The owner is told", "The page shows a toast and, where the owner allowed it, a "
               "browser notification, with the distractions that were parked during the session.",
               ["events", "ui", "owner", "scratch"], [("events", "ui"), ("ui", "owner")]),
     ]},
    {"id": "quarantine", "title": "An injected email", "kind": "defence",
     "about": "Mail that addresses the assistant is withheld before the model can read it.",
     "steps": [
         _step("A message arrives", "A message from an unknown sender is in the mailbox. Its text "
               "addresses an assistant and tells it to act.", ["practice", "mcp_mail", "gateway"],
               [("mcp_mail", "practice"), ("gateway", "mcp_mail")]),
         _step("Triage is asked for", "The owner asks for triage. The responder calls triage_inbox, "
               "and triage reads the threads through the allowlist and the gateway.",
               ["owner", "ui", "api", "call_model", "dispatch_tools", "tools", "triage", "allowlist",
                "gateway", "mcp_mail"],
               [("owner", "ui"), ("ui", "api"), ("call_model", "dispatch_tools"),
                ("dispatch_tools", "tools"), ("tools", "triage"), ("triage", "allowlist"),
                ("allowlist", "gateway"), ("gateway", "mcp_mail")]),
         _step("The harness decides, not the model", "The shared policy rates the sender from the "
               "contacts and runs the tripwire over the text, before the reasoning model has seen "
               "the message. System One is asked the same question when it is on, and either "
               "detector is enough.", ["triage", "policy", "untrusted", "system_one", "t_contacts"],
               [("triage", "policy"), ("triage", "untrusted"), ("untrusted", "policy"),
                ("untrusted", "system_one"), ("triage", "t_contacts")]),
         _step("The thread is quarantined", "An unknown sender with a tripwire hit gets the category "
               "quarantine. The sender's name, the subject and the text are withheld; only the "
               "thread ID and the category are returned.", ["untrusted", "triage", "tools",
                                                           "dispatch_tools"],
               [("triage", "untrusted"), ("tools", "triage"), ("dispatch_tools", "tools")]),
         _step("The model sees no text", "The responder receives the row without its text, so the "
               "text cannot instruct it. It reports the thread by its ID.",
               ["dispatch_tools", "call_model", "claude", "scripted"],
               [("dispatch_tools", "call_model"), ("call_model", "claude"),
                ("call_model", "scripted")]),
         _step("Replies are refused", "The mail tools refuse to draft or send a reply to a "
               "quarantined thread, whatever the responder asks for. A gated action that names the "
               "thread is marked as a risk.", ["dispatch_tools", "tools", "approval_gate", "t_audit"],
               [("dispatch_tools", "tools"), ("approval_gate", "t_audit")]),
         _step("The owner can read it", "The page shows the quarantined text to a person who asks "
               "for it, never to the model. The tripwire misses most attacks, so the wrapper and "
               "the approval gate stay the main defences.", ["ui", "owner", "untrusted", "persist",
                                                           "events"],
               [("persist", "events"), ("events", "ui"), ("ui", "owner")]),
     ]},
]

# The implementation ledger. ``part`` names the component a row belongs to.
LEDGER: list[dict[str, str]] = [
    {"concern": "Agent loop", "component": "LangGraph StateGraph", "part": "call_model",
     "role": "Context, model, tools, approval and persistence as explicit nodes", "status": "built"},
    {"concern": "Model adapter", "component": "ChatAnthropic, adaptive thinking", "part": "claude",
     "role": "Reasoning and tool selection with automatic tool choice", "status": "built-needs-key"},
    {"concern": "Scripted responder", "component": "Deterministic intent router", "part": "scripted",
     "role": "Runs the same loop and tools with no credentials", "status": "built"},
    {"concern": "Append-only context", "component": "Frozen system prompt and tool list",
     "part": "assemble_context",
     "role": "What changes travels in the first user message of each turn", "status": "built"},
    {"concern": "Systems of record", "component": "Workspace gateway over MCP", "part": "gateway",
     "role": "Mail, calendar and notes read on demand, never mirrored", "status": "built"},
    {"concern": "Tool allowlist", "component": "Harness allowlist with three tiers", "part": "allowlist",
     "role": "Automatic, approval and never exposed", "status": "built"},
    {"concern": "Trusted tools", "component": "Typed schemas with a reason on every write",
     "part": "tools", "role": "The only path from the model to an effect", "status": "built"},
    {"concern": "Approval gate", "component": "interrupt() and Command(resume=...)",
     "part": "human_review",
     "role": "A gated action pauses the run; the decision resumes the same run", "status": "built"},
    {"concern": "Action log", "component": "ppa_action_audit", "part": "t_audit",
     "role": "What was done, why, and what was really delivered", "status": "built"},
    {"concern": "Safe mode", "component": "Workspace gateway", "part": "safe_mode",
     "role": "Approved mail to other people is held as a draft until switched off", "status": "built"},
    {"concern": "Untrusted content", "component": "policy.wrap_untrusted", "part": "untrusted",
     "role": "Mail, notes, web and invitation text reach the model as delimited data",
     "status": "built"},
    {"concern": "Injection tripwire", "component": "policy.detect_injection", "part": "untrusted",
     "role": "Quarantines instruction-like mail from unknown senders", "status": "partial-low-recall"},
    {"concern": "Recipient risk", "component": "policy.recipient_risk", "part": "approval_gate",
     "role": "Flags a recipient who is not on the thread or not a known contact", "status": "built"},
    {"concern": "Long-term memory", "component": "LocalMemoryProvider", "part": "memory_provider",
     "role": "Preferences, people, commitments and facts with a time to live",
     "status": "partial-keyword-recall"},
    {"concern": "Episodic memory", "component": "Workday episode at session end", "part": "scratch",
     "role": "A record of each day, recalled in later sessions", "status": "partial-computed-summary"},
    {"concern": "Workday scratch pad", "component": "ScratchFS", "part": "scratch",
     "role": "Quick capture, the day plan and working notes", "status": "built"},
    {"concern": "Promotion", "component": "Promotion queue with content hashes", "part": "t_scratch",
     "role": "Selected notes become tasks or memories once", "status": "built"},
    {"concern": "Forgetting", "component": "Fade, stale detection and expiry sweep",
     "part": "t_memories",
     "role": "Done items fade, stale tasks become candidates to drop", "status": "built"},
    {"concern": "Governed meaning", "component": "Shared policy functions", "part": "policy",
     "role": "One definition each for urgent, free, VIP and over-booked", "status": "built"},
    {"concern": "Tasks", "component": "ppa_tasks", "part": "t_tasks",
     "role": "The running to-do list and its source links", "status": "built"},
    {"concern": "Calendar intelligence", "component": "Free slots, load, time-blocking, meeting prep",
     "part": "calendar", "role": "Plans around real events and the owner's rules", "status": "built"},
    {"concern": "Focus runtime", "component": "Pomodoro sessions with one-shot jobs", "part": "focus",
     "role": "Timers that survive a restart", "status": "built"},
    {"concern": "Scheduler", "component": "Thread polling ppa_automation_queue", "part": "scheduler",
     "role": "Fires timers and routines; DBMS_SCHEDULER in the notebook", "status": "built-mirror"},
    {"concern": "Proactive routines", "component": "Schedules and event triggers", "part": "routines",
     "role": "Enter through the same agent entry point as chat", "status": "built"},
    {"concern": "Context and cost ledger", "component": "ppa_model_calls, prompt caching on",
     "part": "ledger", "role": "Fresh, written and read tokens, seconds and cost for every model call",
     "status": "built"},
    {"concern": "Trajectories", "component": "ppa_turns", "part": "trajectories",
     "role": "One row for each turn, opened at the start and closed at the end", "status": "built"},
    {"concern": "Learning from traces", "component": "Workflow to skill, gate, refine, roll back",
     "part": "learning", "role": "Five checks before a candidate goes live; nothing is deleted",
     "status": "built"},
    {"concern": "Scorecard", "component": "Frozen checks and one verdict", "part": "scorecard",
     "role": "READY or BLOCKED, computed from the records", "status": "built"},
    {"concern": "Skills", "component": "ppa_skill_registry, versions in ppa_skill_versions", "part": "skills",
     "role": "Manifests always visible, one body loaded on demand",
     "status": "partial-keyword-retrieval"},
    {"concern": "Checkpoints", "component": "LangGraph checkpoint saver", "part": "t_checkpoints",
     "role": "Durable graph state; OracleSaver in the notebook", "status": "built-mirror"},
    {"concern": "Database substrate", "component": "Local store, one file per owner", "part": "database",
     "role": "Holds the tables the harness owns, on this machine", "status": "partial-local-only"},
    {"concern": "Window on Oracle AI Database", "component": "python-oracledb, thin mode, read-only",
     "part": "oracle",
     "role": "Shows what the notebook's harness left in Oracle; the appbook stores nothing there",
     "status": "built"},
    {"concern": "Data explorer", "component": "Read-only table browser", "part": "database",
     "role": "A fixed list of tables, bound parameters, a hard row limit", "status": "built"},
    {"concern": "Web search", "component": "Tavily", "part": "tavily",
     "role": "Dated outside evidence, delimited as untrusted", "status": "built-needs-key"},
    {"concern": "Prompt caching", "component": "Top-level ephemeral breakpoint", "part": "claude",
     "role": "Re-reads the stable prefix inside a multi-step turn", "status": "built-needs-key"},
    {"concern": "Answer streaming", "component": "Trace events over SSE", "part": "events",
     "role": "Steps stream live; the answer text arrives whole", "status": "partial-no-token-stream"},
    {"concern": "Embedding model", "component": "None", "part": "embedding",
     "role": "Recall and skill ranking use keyword overlap, not vectors",
     "status": "partial-keyword-overlap"},
    {"concern": "Trace export", "component": "LangSmith, by environment switch", "part": "langsmith",
     "role": "The libraries export traces when the environment asks; the appbook adds no exporter",
     "status": "partial-library-only"},
    {"concern": "Semantic cache", "component": "None", "part": "",
     "role": "Mail, calendar and tasks change outside the database, so a cached answer would be stale",
     "status": "not-implemented-by-design"},
    {"concern": "System One model", "component": "Jev, with rules as the fallback", "part": "system_one",
     "role": "Screens mail for attacks and chooses the evidence for meeting preparation. Every tool "
             "is still offered to the model, so that the prompt prefix stays stable and cached",
     "status": "partial"},
    {"concern": "Multi-agent orchestration", "component": "None", "part": "",
     "role": "One agent handles every request", "status": "missing"},
    {"concern": "Code sandbox", "component": "None", "part": "",
     "role": "The assistant runs no generated code", "status": "missing"},
    {"concern": "Accounts and sign-in", "component": "None", "part": "",
     "role": "One owner on one machine", "status": "missing"},
]

PACKAGES = ("fastapi", "uvicorn", "sse-starlette", "pydantic", "langgraph",
            "langchain-core", "langchain-anthropic", "langchain-mcp-adapters", "mcp", "tavily-python",
            "langsmith", "httpx", "oracledb")


def _engine() -> str:
    """The version of whatever holds the harness tables."""
    if not store.oracle():
        return f"SQLite {sqlite3.sqlite_version}"
    try:
        return f"Oracle AI Database {oracle_store.version(world.identity())}"
    except Exception:          # the status check below reports the failure; this is only a label
        return "Oracle AI Database"


ON_ORACLE = (
    ("Local store, one file per owner", "Oracle AI Database, one schema per owner"),
    ("A table in the local store", "A table in Oracle AI Database"),
    ("in the appbook's local store", "in the appbook's schema in Oracle AI Database"),
    ("the appbook keeps in its local store", "the appbook keeps in its own schema"),
    ("on the local store", "on Oracle AI Database"),
    ("in the local store", "in Oracle AI Database"),
    ("one file per owner", "one schema per owner"),
    ("Local store", "Oracle AI Database"),
    ("local store", "Oracle AI Database"),
)


def worded(value: Any) -> Any:
    """Name the store as it is. The structure was written for the local store; on Oracle
    the same sentences name Oracle."""
    if not store.oracle():
        return value
    if isinstance(value, str):
        for old, new in ON_ORACLE:
            value = value.replace(old, new)
        return value
    if isinstance(value, dict):
        return {key: worded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [worded(item) for item in value]
    return value


def versions() -> dict[str, str]:
    found = {"python": ".".join(str(part) for part in sys.version_info[:3]),
             "store engine": _engine()}
    for name in PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "not installed"
    return found


VERSION_OF: dict[str, tuple[str, ...]] = {
    "api": ("fastapi", "uvicorn", "pydantic"), "events": ("sse-starlette",), "tools": ("pydantic",),
    "claude": ("langchain-anthropic", "langchain-core"), "scripted": ("python",),
    "database": ("store engine",), "oracle": ("oracledb",), "t_checkpoints": ("langgraph",),
    "allowlist": ("langchain-mcp-adapters", "httpx"), "gateway": ("mcp",), "tavily": ("tavily-python",),
    "langsmith": ("langsmith",),
    **{name: ("langgraph",) for name in NODES},
    **{f"mcp_{name}": ("mcp",) for name in SYSTEMS},
}


# ── Observation: everything the checks read, gathered once per request ───────

async def observe(routes: int = 0) -> dict[str, Any]:
    seen: dict[str, Any] = {"routes": routes, "gateway_error": None, "effects": None}
    seen["tables"] = {item["name"]: item for item in explorer.tables()}
    seen["graph"] = set(agent.compiled.get_graph().nodes) if agent.compiled is not None else set()
    if await workspace.probe() is None:
        seen["gateway_error"] = "The gateway did not answer its health check"
    else:
        try:
            seen["effects"] = await workspace.effects()
            seen["providers"] = await workspace.providers()
        except WorkspaceError as exc:
            seen["gateway_error"] = str(exc)
    seen["health"] = workspace.health if seen["gateway_error"] is None else {}
    seen["offered"] = workspace.catalogue()
    seen["provenance"] = workspace.provenance or {}
    seen["actions"] = {item["state"]: item["total"] for item in store.rows(
        "SELECT state, COUNT(*) AS total FROM ppa_action_audit GROUP BY state")}
    seen["jobs"] = {item["state"]: item["total"] for item in store.rows(
        "SELECT state, COUNT(*) AS total FROM ppa_automation_queue GROUP BY state")}
    seen["triggered"] = store.row("SELECT COUNT(*) AS total FROM ppa_automation_queue "
                                  "WHERE kind IN ('meeting_prep','vip_alert')")
    seen["gated"] = store.row("SELECT COUNT(*) AS total FROM ppa_action_audit WHERE tier='approval'")
    seen["runs"] = agent.runs(limit=200)
    seen["scheduler"] = scheduler.status()
    seen["llm"] = llm_client.status()
    seen["tracing"] = tracing.status()
    seen["bus"] = bus.status()
    seen["clock"] = clock.status()
    seen["schedules"] = store.rows("SELECT enabled FROM ppa_schedules")
    seen["running"] = store.row("SELECT COUNT(*) AS total FROM ppa_focus_sessions WHERE status='RUNNING'")
    seen["memories"] = store.row("SELECT COUNT(*) AS total FROM ppa_memories WHERE status='ACTIVE'")
    seen["skills"] = store.row("SELECT COUNT(*) AS total FROM ppa_skill_registry WHERE status='ACTIVE'")
    seen["contacts"] = len(world.contacts())
    seen["oracle"] = await asyncio.to_thread(oracle_window.probe)
    return seen


def _result(status: str, detail: str, label: str | None = None, value: Any = None) -> dict[str, Any]:
    return {"status": status, "detail": detail,
            "metric": None if label is None else {"label": label, "value": value}}


def _named(names: list[str]) -> list[str]:
    """The tables of a component under the names this substrate gives them."""
    if not store.oracle():
        return names
    return [item for name in names for item in (list(explorer.ON_ORACLE) if name == "writes" else [name])]


def _rows(seen: dict[str, Any], names: list[str]) -> tuple[bool, int]:
    found = [seen["tables"].get(name) for name in _named(names)]
    return all(item and item["columns"] for item in found), sum(item["row_count"] for item in found if item)


def _node(name: str, label: str, count: Callable[[dict[str, Any]], int]) -> Callable:
    def check(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
        if name not in seen["graph"]:
            return _result("failing", "The compiled graph has no node of this name")
        return _result("connected", "A node of the compiled graph", label, count(seen))
    return check


def _tables(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    present, total = _rows(seen, part["artefacts"]["tables"])
    if not present:
        return _result("failing", "A table is missing from the store")
    return _result("connected", "Read from the database just now", "rows", total)


def _service(label: str, count: Callable[[dict[str, Any]], Any], detail: str = "Loaded in this process"):
    def check(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
        tables = part["artefacts"]["tables"]
        if tables and not _rows(seen, tables)[0]:
            return _result("failing", "A table this service writes to is missing")
        found = f"; {', '.join(tables)} read just now" if tables else ""
        return _result("connected", f"{detail}{found}", label, count(seen))
    return check


def _gateway_up(seen: dict[str, Any]) -> bool:
    return seen["gateway_error"] is None


def _owner(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    persona = world.persona()
    return _result("connected", f"Persona loaded from the gateway; working hours {persona['work_start']} "
                                f"to {persona['work_end']}, {persona['timezone']}",
                   "contacts", seen["contacts"])


def _ui(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    listening = seen["bus"]["listeners"]
    if listening:
        return _result("connected", "A page is listening to the event stream", "pages listening", listening)
    return _result("off", "No page is listening to the event stream", "pages listening", 0)


def _api(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    return _result("connected", "It answered this request", "routes", seen["routes"])


def _claude(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    llm = seen["llm"]
    if not llm["key_present"]:
        return _result("not_configured", "ANTHROPIC_API_KEY is not set. The scripted responder answers.")
    if not llm["claude_available"]:
        return _result("off", "A key is configured, but PPA_RESPONDER=scripted keeps the scripted "
                              "responder in charge.")
    mine = [run for run in seen["runs"] if run["responder"] != scripted.LABEL]
    if not mine:
        return _result("configured", f"{settings.anthropic_model}: a key is configured. No run has "
                                     "called the model yet.", "runs", 0)
    last = mine[0]
    seconds = round((last["trace"].get("latency_ms") or 0) / 1000, 1)
    if last["status"] == "failed":
        return _result("failing", f"The last run failed: {str(last.get('answer') or '')[:160]}",
                       "runs", len(mine))
    return _result("connected", f"{settings.anthropic_model}: the last run {last['status']} "
                                f"after {seconds} s", "last run, seconds", seconds)


def _scripted(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    mine = sum(run["responder"] == scripted.LABEL for run in seen["runs"])
    if seen["llm"]["responder"] == "scripted":
        return _result("fallback", "It answers every request, because Claude is not in use", "runs", mine)
    return _result("connected", "It writes timer summaries; Claude answers everything else", "runs", mine)


def _embedding(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    return _result("fallback", f"{memory_provider.name}: recall by keyword overlap. No embedding model "
                               "is installed or called.")


def _memory(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if not _rows(seen, ["ppa_memories"])[0]:
        return _result("failing", "The memory table is missing")
    return _result("fallback", "The local provider with keyword recall. Oracle Agent Memory and vector "
                               "search are used in the notebook.", "active memories",
                   seen["memories"]["total"])


def _database(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    ready = [name for name, item in seen["tables"].items() if item["columns"]]
    if len(ready) < len(explorer.listed()):
        return _result("failing", f"{len(explorer.listed()) - len(ready)} tables are missing")
    where = "one schema per owner" if store.oracle() else "one file per owner on this machine"
    return _result("connected", f"{store.SUBSTRATE}: {where}, read just now", "tables", len(ready))


def _oracle(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    found = seen["oracle"]
    if not found["reachable"]:
        return _result("off", f"Not reachable at {settings.oracle_dsn}. {oracle_window.HOW} Nothing in "
                              "the appbook depends on it.")
    if found["tables"] is None:
        return _result("connected", f"Reachable at {settings.oracle_dsn}, and busy: it did not answer "
                                    "within two seconds")
    return _result("connected", f"Oracle AI Database {found['version']} at {settings.oracle_dsn}, read "
                                f"as {settings.oracle_user}, read-only", "tables", found["tables"])


def _scheduler(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    state = seen["scheduler"]
    armed = seen["jobs"].get("ARMED", 0)
    if not state["running"]:
        return _result("failing", "The scheduler thread is not running", "armed jobs", armed)
    if not state["automation_enabled"]:
        return _result("off", "Routines and triggers are paused. Focus timers still fire.",
                       "armed jobs", armed)
    return _result("connected", f"The thread is polling every {state['poll_seconds']} s", "armed jobs",
                   armed)


def _routines(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    enabled = sum(bool(item["enabled"]) for item in seen["schedules"])
    if not seen["scheduler"]["automation_enabled"]:
        return _result("off", "Automation is paused, so no routine runs by itself",
                       "schedules enabled", enabled)
    return _result("connected", "Each schedule has a job armed for its next occurrence",
                   "schedules enabled", enabled)


def _triggers(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    armed = seen["triggered"]["total"]
    if not seen["scheduler"]["automation_enabled"]:
        return _result("off", "Automation is paused, so no trigger is checked", "jobs armed by a trigger",
                       armed)
    return _result("connected", f"Checked every {settings.trigger_poll_seconds:g} s, and whenever the "
                                "clock is moved", "jobs armed by a trigger", armed)


def _system_one(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    state = system_one.status()
    if not state["available"]:
        why = "TYPESAFE_API_KEY is not set" if not state["configured"] else "switched off"
        return _result("fallback", f"System One is off ({why}), so rules decide. "
                                   + approval.TRIPWIRE_FINDING["statement"], "tripwire patterns",
                       len(policy.INJECTION_PATTERNS))
    if state["failed"] and not state["decisions"]:
        return _result("failing", "System One was asked and did not answer. Rules decided instead.",
                       "failed calls", state["failed"])
    return _result("connected", f"{state['model']} answers, and the harness owns the thresholds",
                   "decisions logged", state["decisions"])


def _clock(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    state = seen["clock"]
    about = {"practice": "Pinned by the practice workspace", "pinned": "Pinned by the owner",
             "real": "The real clock, in the owner's timezone"}[state["mode"]]
    return _result("connected", f"{about}: {state['now']}", "mode", state["mode"])


def _events(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if bus.loop is None:
        return _result("failing", "The bus is not bound to the server's event loop")
    return _result("connected", f"{seen['bus']['listeners']} pages listening", "events published",
                   seen["bus"]["published"])


def _untrusted(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    return _result("connected", approval.TRIPWIRE_FINDING["statement"], "tripwire patterns",
                   len(policy.INJECTION_PATTERNS))


def _gateway(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    offered = sum(len(items) for items in seen["offered"].values())
    if not _gateway_up(seen):
        return _result("failing", seen["gateway_error"], "tools offered", offered)
    owner = "started by the appbook" if workspace.owned else "already running, reused"
    return _result("connected", f"{settings.mcp_base_url}, {owner}, {seen['health'].get('mode')} mode",
                   "tools offered", offered)


def _allowlist(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    offered = {item["name"] for items in seen["offered"].values() for item in items}
    missing = sorted(set(ALLOWLIST) - offered)
    if missing:
        return _result("failing", f"The gateway does not offer: {', '.join(missing)}",
                       "tools allowed", len(ALLOWLIST))
    return _result("connected", f"{len(ALLOWLIST)} of the {len(offered)} tools the servers offer can "
                                "be reached", "tools allowed", len(ALLOWLIST))


def _server(name: str) -> Callable:
    def check(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
        offered = len(seen["offered"].get(name, []))
        if not _gateway_up(seen):
            return _result("failing", seen["gateway_error"], "tools offered", offered)
        system = seen["health"].get("systems", {}).get(name, {})
        if not system.get("connected"):
            return _result("failing", str(system.get("detail") or "The provider is not answering"),
                           "tools offered", offered)
        return _result("connected", f"Provider: {system.get('provider')}", "tools offered", offered)
    return check


def _safe_mode(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if not _gateway_up(seen):
        return _result("failing", seen["gateway_error"])
    held = sum(item.get("status") == "held_by_safe_mode" for item in seen["effects"] or [])
    if not seen["health"].get("safe_mode", True):
        return _result("off", "Approved actions are delivered for real", "effects held", held)
    scope = "It has nothing to hold in the practice workspace, where no one can be reached." \
        if workspace.practising() else "Approved mail to other people is held as a draft."
    return _result("connected", f"On. {scope}", "effects held", held)


def _effects(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if seen["effects"] is None:
        return _result("failing", seen["gateway_error"] or "The effect log could not be read")
    return _result("connected", "Read from the gateway just now", "effects", len(seen["effects"]))


def _practice(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if not _gateway_up(seen):
        return _result("failing", seen["gateway_error"])
    sources = seen["provenance"].get("sources", {})
    named = "; ".join(item["dataset"] + (f" ({item['licence']} licence)" if item.get("licence") else "")
                      for item in sources.values() if item.get("dataset"))
    received = (seen["provenance"].get("counts") or {}).get("received")
    if not workspace.practising():
        return _result("off", "A real account is connected, so the practice data is not in use")
    return _result("connected", f"Datasets: {named}" if named else "In use", "messages received", received)


def _connector_check(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if not _gateway_up(seen):
        return _result("failing", seen["gateway_error"])
    offered = {item["id"] for item in (seen.get("providers") or {}).get(part["system"], [])}
    if part["id"] not in offered:
        return _result("failing", "The gateway does not offer this provider")
    system = seen["health"].get("systems", {}).get(part["system"], {})
    if system.get("provider") == part["id"]:
        if system.get("connected"):
            return _result("connected", str(system.get("detail") or "Connected"))
        return _result("failing", str(system.get("detail") or "The connection is not answering"))
    return _result("not_configured", "Not connected. The practice workspace is in use.")


def _tavily(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    if websearch.configured():
        return _result("configured", "TAVILY_API_KEY is set. The key is used on the next search.")
    return _result("not_configured", "TAVILY_API_KEY is not set. The tool answers that web search is "
                                     "not configured.")


def _langsmith(seen: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    state = seen["tracing"]
    if not state["requested"]:
        return _result("off", state["detail"])
    if not state["configured"]:
        return _result("not_configured", state["detail"])
    return _result("configured", state["detail"])


def _count(table: str) -> Callable[[dict[str, Any]], int]:
    return lambda seen: seen["tables"][table]["row_count"]


CHECKS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "owner": _owner, "ui": _ui, "api": _api,
    "assemble_context": _node("assemble_context", "active memories", lambda seen: seen["memories"]["total"]),
    "call_model": _node("call_model", "model calls recorded", lambda seen: sum(
        run["trace"].get("model_calls") or 0 for run in seen["runs"])),
    "dispatch_tools": _node("dispatch_tools", "tools the model can call", lambda seen: len(tools.schemas())),
    "draft_effects": _node("draft_effects", "gated actions drafted", lambda seen: seen["gated"]["total"]),
    "human_review": _node("human_review", "waiting for a decision",
                          lambda seen: seen["actions"].get("DRAFTED", 0)),
    "apply_effects": _node("apply_effects", "actions executed",
                           lambda seen: seen["actions"].get("EXECUTED", 0)),
    "persist": _node("persist", "runs stored", _count("ppa_agent_runs")),
    "tools": _service("tools registered", _count("ppa_tool_registry")),
    "approval_gate": _service("waiting for a decision", lambda seen: seen["actions"].get("DRAFTED", 0)),
    "policy": _service("governed definitions", lambda seen: len(governed.definitions()),
                       "Imported from the shared runtime folder"),
    "untrusted": _untrusted,
    "triage": _service("threads read for one triage", lambda seen: settings.triage_window),
    "calendar": _service("tasks planned for today", lambda seen: store.row(
        "SELECT COUNT(*) AS total FROM ppa_tasks WHERE status='OPEN' AND planned_for=?",
        (clock.today().isoformat(),))["total"]),
    "skills": _service("active skills", lambda seen: seen["skills"]["total"]),
    "memory_provider": _memory,
    "scratch": _service("scratch files", _count("ppa_scratch_files")),
    "focus": _service("sessions running", lambda seen: seen["running"]["total"]),
    "scheduler": _scheduler, "routines": _routines, "triggers": _triggers,
    "handler": _service("notifications delivered", _count("ppa_notifications")),
    "system_one": _system_one,
    "review": _service("focus sessions recorded", _count("ppa_focus_sessions")),
    "ledger": _service("model calls recorded", _count("ppa_model_calls")),
    "trajectories": _service("turns recorded", _count("ppa_turns")),
    "learning": _service("skill versions stored", _count("ppa_skill_versions")),
    "scorecard": _service("blocking checks", lambda seen: sum(
        1 for item in scorecard.CHECKS if item["blocking"]), "Computed from the store when the chapter asks"),
    "clock": _clock, "events": _events,
    "claude": _claude, "scripted": _scripted, "embedding": _embedding,
    "database": _database, "oracle": _oracle,
    **{name: _tables for name in ("t_tasks", "t_focus", "t_queue", "t_schedules", "t_notifications",
                                  "t_audit", "t_scratch", "t_memories", "t_skills", "t_tools", "t_runs",
                                  "t_skill_versions", "t_turns", "t_model_calls",
                                  "t_checkpoints", "t_contacts", "t_meta")},
    "allowlist": _allowlist, "gateway": _gateway,
    **{f"mcp_{name}": _server(name) for name in SYSTEMS},
    "safe_mode": _safe_mode, "effects": _effects,
    "practice": _practice,
    **{name: _connector_check for name in ("imap", "google", "ics", "notion", "folder")},
    "tavily": _tavily, "langsmith": _langsmith,
}


def _checked(part: dict[str, Any], seen: dict[str, Any]) -> dict[str, Any]:
    try:
        return CHECKS[part["id"]](seen, part)
    except Exception as exc:          # a check that cannot run is itself a finding
        return _result("failing", f"The check raised {type(exc).__name__}: {str(exc)[:160]}")


def _tools_of(part: dict[str, Any], seen: dict[str, Any]) -> list[dict[str, Any]]:
    """The tools behind a component, with the tier the harness gives each."""
    identity = part["id"]
    if identity == "tools":
        return [{"name": tool.name, "tier": tool.tier, "source": tool.source}
                for tool in tools.TOOLS.values() if tool.model_facing]
    if identity == "allowlist":
        return [{"name": name, "tier": tier, "source": "mcp:" + name.split("_", 1)[0]}
                for name, tier in ALLOWLIST.items()]
    if identity.startswith("mcp_"):
        return [{"name": item["name"], "tier": item["tier"], "source": identity.replace("_", ":")}
                for item in seen["offered"].get(identity[4:], [])]
    return [{"name": name, "tier": tools.TOOLS[name].tier, "source": tools.TOOLS[name].source}
            for name in part["artefacts"]["tools"] if name in tools.TOOLS]


def _version(identity: str, found: dict[str, str]) -> str:
    return ", ".join(f"{name} {found[name]}" for name in VERSION_OF.get(identity, ()))


def ledger() -> dict[str, Any]:
    rows = []
    for item in LEDGER:
        status = item["status"]
        if status == "built-needs-key":
            ready = websearch.configured() if item["part"] == "tavily" else settings.claude_available
            status = "built" if ready else "built-inactive-no-key"
        rows.append({**item, "status": status})
    counts = {
        "built": sum(item["status"].startswith("built") for item in rows),
        "partial": sum(item["status"].startswith("partial") for item in rows),
        "missing": sum(item["status"].startswith("missing") for item in rows),
        "not_implemented_by_design": sum(item["status"].startswith("not-implemented") for item in rows),
    }
    return {"ledger": rows, "counts": counts}


async def statuses(routes: int = 0) -> dict[str, Any]:
    """Live status only: what the page asks for while the view is open."""
    with store.quiet():
        seen = await observe(routes)
        return worded({"checked_at": store.real_now(),
                       "components": {part["id"]: _checked(part, seen) for part in COMPONENTS}})


async def snapshot(routes: int = 0) -> dict[str, Any]:
    """The whole structure with a live status on every component."""
    found = versions()
    parts = []
    with store.quiet():
        seen = await observe(routes)
        for part in COMPONENTS:
            artefacts = {**part["artefacts"], "tables": _named(part["artefacts"]["tables"]),
                         "tools": _tools_of(part, seen)}
            parts.append({**part, "artefacts": artefacts, "version": _version(part["id"], found),
                          **_checked(part, seen)})
    return worded({
        "chapter": "Architecture", "checked_at": store.real_now(), "statuses": STATUSES,
        "tiers": TIER_RULES, "lanes": LANES, "components": parts,
        "edges": [{"from": source, "to": target, "label": label, "main": main}
                  for source, target, label, main in EDGES],
        "paths": PATHS, **ledger(), "versions": found, "substrate": store.SUBSTRATE,
        "responder": seen["llm"]["label"],
        "teaching_point": "Mail, calendar and notes stay in their systems of record. The harness "
                          "owns only what has no other home: tasks, focus sessions, memory, the "
                          "action log and its own checkpoints."})
