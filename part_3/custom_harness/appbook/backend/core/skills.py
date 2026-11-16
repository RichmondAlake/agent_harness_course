"""Skills with progressive disclosure and versions.

A manifest is a name and a sentence. A body is a procedure. Every turn carries
the manifests of the live skills; a body enters the context only when
``load_skill`` asks for it.

Three tables hold them.

* ``ppa_skill_versions`` keeps every version ever written: its description,
  its body, a hash of the body, where it came from and what the promotion gate
  said about it. A version is never edited. Only its gate result changes.
* ``ppa_skill_registry`` holds what is live: one row for each active skill,
  with a ``version`` pointer. Only these rows are offered to the model.
* ``ppa_skill_log`` records every move of a pointer: activate, retire, and the
  short trial the gate runs.

``activate`` moves a pointer to any stored version. Rolling back is the same
call with an older number. Nothing is deleted.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from backend.core import store

ORIGINS = ("authored", "learned", "refined")
TRIAL_KEY = "skill_trial"          # set while a gate trial holds a pointer, so a crash can be undone

SKILLS: dict[str, dict[str, Any]] = {
    "morning-brief": {
        "description": "Compose the start-of-day brief: what needs attention first, today's calendar "
                       "with rule breaks, and at most three top tasks.",
        "triggers": ["morning", "brief", "start", "day", "today", "attention"],
        "body": """# Morning brief
1. Call `triage_inbox`, `day_overview` for today and `task_list`.
2. Lead with the first triage row: it has the lowest attention rank. Give the sender, the subject, why it ranks first and the thread ID.
3. List today's events in time order with their IDs. For every event in `meeting_rule_violations`, say which rule it breaks and offer to propose a later time. Responding to an invitation needs approval.
4. List at most three tasks in governed order and mark the urgent ones. If there are no tasks yet, say so and offer to triage the inbox.
5. Name the free slots that can hold a focus session.
6. Report quarantined threads in one line, by ID. Do not open them.
7. Keep it short enough to read in one minute. Sections: Needs you first, Today, Top tasks, Free for focus, Held back.""",
    },
    "inbox-triage": {
        "description": "Sort the inbox by governed category and turn actionable threads into tasks "
                       "and unsent drafts.",
        "triggers": ["triage", "inbox", "email", "mail", "actionable", "tasks", "sort"],
        "body": """# Inbox triage
1. Call `triage_inbox`. The category, VIP flag, tracking and quarantine in each row are decided by the harness. Do not overrule them.
2. `task`: call `task_add` with `source_type` "mail" and `source_ref` set to the thread ID. Read the thread first when you need a due date or a better estimate; set `due_at` only when the message states one.
3. `reply`: call `task_add` for the reply, then `mail_create_draft` addressed to the sender. Never send. For a meeting invitation, create the task only; responding is a separate, approved action.
4. `delegate`: draft a hand-over note to the suggested owner and create one task to follow up.
5. `tracked`: cite the existing task ID. Create nothing.
6. `archive`: count them. Create nothing.
7. `quarantine`: report the thread ID and the pattern names. Do not open, answer or forward it.
8. Summarise as a short list per category, with task IDs and draft IDs.""",
    },
    "meeting-prep": {
        "description": "Prepare a short brief for one meeting from its thread, its page and the last notes.",
        "triggers": ["meeting", "prep", "prepare", "call", "before", "agenda", "brief"],
        "body": """# Meeting prep
1. Find the event: use the ID given, or `day_overview` to pick the next meeting.
2. Call `meeting_prep` with the event ID. It returns the event, the people, the related thread, the related page and the owner's open actions.
3. If earlier mail on the same matter would help, call `mail_search_threads` with label "ALL" and the subject words.
4. Write the brief in this order: purpose in one sentence; who will be there and who is a VIP; what they are waiting for; facts to have ready; the owner's open actions; two questions worth asking.
5. Stay under 150 words. Quote figures exactly as the sources give them and cite thread and page IDs.""",
    },
    "time-block-tasks": {
        "description": "Place the top tasks into today's free slots and ask for approval before "
                       "writing to the calendar.",
        "triggers": ["time", "block", "schedule", "plan", "slots", "calendar", "top", "tasks"],
        "body": """# Time-block tasks
1. Call `task_list` and take the top three in governed order, unless specific tasks were named.
2. Call `plan_time_blocks` with those task IDs. The harness sizes each block by estimated Pomodoros and avoids every existing event.
3. For each block call `calendar_create_event` with kind "focus", the block's start and end, the task title as the title and only the owner as attendee. Issue all the calls together so they are approved in one step.
4. The run pauses for approval. If a block is declined, do not retry it. Say what was not written and leave the plan in `/plans/today.md`.
5. Report the blocks that were created with their event IDs, and any task that did not fit.""",
    },
    "focus-session": {
        "description": "Start, check or stop a Pomodoro tied to a task, and park distractions for the break.",
        "triggers": ["pomodoro", "focus", "timer", "session", "deep", "work", "distraction"],
        "body": """# Focus session
1. Resolve the task with `task_list`. If nothing matches, create the task with `task_add` first.
2. Call `pomodoro_start` with the task ID. Use the owner's default length unless a length was given.
3. While a session runs, anything that is not the task goes to `capture_note`. Do not act on it now.
4. `pomodoro_status` answers how long is left. `pomodoro_stop` ends the session early and records why.
5. When the session ends, list the parked distractions and suggest a break.""",
    },
    "end-of-day-wrap": {
        "description": "Close the workday: what was done, what carries over, tomorrow's first block, "
                       "and which notes to keep.",
        "triggers": ["end", "day", "wrap", "evening", "close", "tomorrow", "carry"],
        "body": """# End-of-day wrap
1. Call `end_of_day_data`. It returns what was completed today, what was planned but is still open, the focus minutes and tomorrow's first free slot.
2. Report three things: done, carried over, and tomorrow's first block with the task that should fill it.
3. List the scratch notes marked for promotion. Notes not marked are left behind.
4. Call `end_workday`. It ends the session, promotes the marked notes and counts one more slip for every planned task that is still open.
5. Close with one sentence. No advice unless something has now slipped twice.""",
    },
    "weekly-review": {
        "description": "Review the week: planned versus done, where time went, what keeps slipping "
                       "and what to drop.",
        "triggers": ["weekly", "week", "review", "slipping", "drop", "time", "went"],
        "body": """# Weekly review
1. Call `weekly_review_data`.
2. Planned versus done: tasks planned or due in the period against tasks completed, then focus minutes planned against minutes achieved.
3. Where time went: minutes by task, largest first, with unplanned time named as such.
4. What keeps slipping: tasks carried over at least twice. Suggest a smaller next step for each.
5. What to drop: open tasks with no due date that nobody has touched for 30 days.
6. End with one decision for next week. If the period holds no data yet, say so plainly.""",
    },
}


def estimate_tokens(text: str) -> int:
    """A stated approximation: four characters to a token."""
    return max(1, round(len(text) / 4))


def sha(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "triggers": [word for word in item["triggers"].split(",") if word],
            "evidence": store.loads(item["evidence"], {}), "gate": store.loads(item["gate"], {})}


def version(name: str, number: int) -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_skill_versions WHERE skill_name=? AND version=?", (name, number))
    return _shape(found) if found else None


def versions(name: str | None = None) -> list[dict[str, Any]]:
    """Every stored version, oldest first, each marked with whether the pointer is on it."""
    found = store.rows("SELECT * FROM ppa_skill_versions ORDER BY rowid")
    live = live_versions()
    return [{**_shape(item), "live": live.get(item["skill_name"]) == item["version"]}
            for item in found if name is None or item["skill_name"] == name]


def live_versions() -> dict[str, int]:
    return {item["skill_name"]: item["version"]
            for item in store.rows("SELECT skill_name,version FROM ppa_skill_registry")}


def write_version(name: str, description: str, triggers: list[str], body: str, *, origin: str,
                  evidence: dict[str, Any] | None = None, drafted_by: str = "",
                  state: str = "CANDIDATE", gate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Store the next version of a skill. It is not offered to the model until it is activated."""
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {', '.join(ORIGINS)}")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,48}", name):
        raise ValueError("A skill name is lower-case words joined by hyphens.")
    latest = store.row("SELECT MAX(version) AS latest FROM ppa_skill_versions WHERE skill_name=?", (name,))
    number = int(latest["latest"] or 0) + 1
    store.execute(
        "INSERT INTO ppa_skill_versions(skill_name,version,description,triggers,body,body_sha256,origin,"
        "evidence,drafted_by,state,gate,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, number, " ".join(description.split()), ",".join(triggers), body.strip(), sha(body.strip()),
         origin, store.dumps(evidence or {}), drafted_by, state, store.dumps(gate or {}), store.real_now()))
    return version(name, number)


def set_gate(name: str, number: int, state: str, gate: dict[str, Any]) -> dict[str, Any]:
    """The one change a stored version allows: what the gate said about it."""
    if state not in ("CANDIDATE", "PASSED", "FAILED"):
        raise ValueError("state must be CANDIDATE, PASSED or FAILED")
    store.execute("UPDATE ppa_skill_versions SET state=?,gate=? WHERE skill_name=? AND version=?",
                  (state, store.dumps(gate), name, number))
    return version(name, number)


def _log(name: str, number: int | None, action: str, reason: str) -> None:
    store.execute("INSERT INTO ppa_skill_log(skill_name,version,action,reason,created_at) VALUES (?,?,?,?,?)",
                  (name, number, action, reason[:400], store.real_now()))


def activate(name: str, number: int, reason: str, *, action: str = "activate") -> dict[str, Any]:
    """Move the live pointer of a skill to a stored version, and log the move."""
    found = version(name, number)
    if found is None:
        raise KeyError(f"{name} has no version {number}")
    store.execute(
        "INSERT INTO ppa_skill_registry(skill_name,description,triggers,body,body_sha256,status,updated_at,"
        "version,origin) VALUES (?,?,?,?,?,'ACTIVE',?,?,?) ON CONFLICT(skill_name) DO UPDATE SET "
        "description=excluded.description,triggers=excluded.triggers,body=excluded.body,"
        "body_sha256=excluded.body_sha256,updated_at=excluded.updated_at,version=excluded.version,"
        "origin=excluded.origin",
        (name, found["description"], ",".join(found["triggers"]), found["body"], found["body_sha256"],
         store.real_now(), number, found["origin"]))
    _log(name, number, action, reason)
    return found


def retire(name: str, reason: str, *, action: str = "retire") -> bool:
    """Remove the live row. Every version stays in the history and can be activated again."""
    live = store.row("SELECT version FROM ppa_skill_registry WHERE skill_name=?", (name,))
    if live is None:
        return False
    store.execute("DELETE FROM ppa_skill_registry WHERE skill_name=?", (name,))
    _log(name, live["version"], action, reason)
    return True


@contextmanager
def trial(name: str, number: int) -> Iterator[None]:
    """Make one version live for the length of a gate run, then put the pointer back.

    The pointer is restored whatever happens inside. A note in ``ppa_meta`` lets the next
    start-up restore it too, should the process stop in the middle.
    """
    before = live_versions().get(name)
    store.set_meta(TRIAL_KEY, store.dumps({"name": name, "before": before}))
    activate(name, number, "gate trial", action="trial")
    try:
        yield
    finally:
        _restore(name, before)


def _restore(name: str, before: int | None) -> None:
    if before is None:
        retire(name, "gate trial ended", action="restore")
    else:
        activate(name, before, "gate trial ended", action="restore")
    store.set_meta(TRIAL_KEY, None)


def log(limit: int = 80) -> list[dict[str, Any]]:
    return store.rows("SELECT * FROM ppa_skill_log ORDER BY rowid DESC LIMIT ?", (limit,))


def sync_registry() -> None:
    """Make sure every authored skill has its first version, and a live row unless it was retired."""
    held = store.loads(store.get_meta(TRIAL_KEY), None)
    if held:                                   # a gate trial was cut short: put the pointer back
        _restore(held["name"], held["before"])
    stored: dict[str, list[dict[str, Any]]] = {}
    for item in store.rows("SELECT skill_name,version,body_sha256,origin FROM ppa_skill_versions "
                           "ORDER BY rowid", trace=False):
        stored.setdefault(item["skill_name"], []).append(item)
    live = live_versions()
    moved = {item["skill_name"] for item in store.rows("SELECT skill_name FROM ppa_skill_log", trace=False)}
    for name, spec in SKILLS.items():
        authored = [item for item in stored.get(name, []) if item["origin"] == "authored"]
        if authored and authored[-1]["body_sha256"] == sha(spec["body"].strip()):
            number = authored[-1]["version"]
            fresh = False
        else:                                  # first start, or the authored text changed in the code
            number = write_version(name, spec["description"], spec["triggers"], spec["body"],
                                   origin="authored", drafted_by="the appbook's authors", state="PASSED",
                                   gate={"note": "Authored and shipped with the appbook."})["version"]
            fresh = True
        if name not in moved or (fresh and name in live and len(authored) >= 1
                                 and live[name] == authored[-1]["version"]):
            activate(name, number, "shipped with the appbook")


def registry() -> list[dict[str, Any]]:
    """The live skills, in the order they are offered."""
    return [{"name": item["skill_name"], "description": item["description"], "version": item["version"],
             "origin": item["origin"], "body_sha256": item["body_sha256"],
             "triggers": item["triggers"].split(","), "updated_at": item["updated_at"]}
            for item in store.rows("SELECT * FROM ppa_skill_registry WHERE status='ACTIVE' ORDER BY rowid")]


def manifests() -> list[dict[str, Any]]:
    """Compact metadata only: what every turn carries."""
    return [{"name": item["skill_name"], "description": item["description"]} for item in store.rows(
        "SELECT skill_name,description FROM ppa_skill_registry WHERE status='ACTIVE' ORDER BY rowid")]


def manifest_text() -> str:
    return "\n".join(f"- {item['name']}: {item['description']}" for item in manifests())


def load(name: str) -> dict[str, Any] | None:
    """Disclose one full body."""
    found = store.row("SELECT * FROM ppa_skill_registry WHERE skill_name=? AND status='ACTIVE'", (name,))
    if found is None:
        return None
    return {"name": found["skill_name"], "description": found["description"], "body": found["body"],
            "body_sha256": found["body_sha256"], "version": found["version"], "origin": found["origin"],
            "tokens": estimate_tokens(found["body"])}


def rank(query: str, *, ignore: str | None = None) -> list[dict[str, Any]]:
    """Rank manifests for a request by overlap with their triggers and descriptions."""
    words = set(re.findall(r"[a-z]+", query.lower()))
    ranked = []
    for item in store.rows("SELECT * FROM ppa_skill_registry WHERE status='ACTIVE' ORDER BY rowid"):
        if item["skill_name"] == ignore:
            continue
        hits = words & set(item["triggers"].split(","))
        described = words & set(re.findall(r"[a-z]+", item["description"].lower()))
        name_hits = words & set(item["skill_name"].split("-"))
        score = len(hits) * 3 + len(name_hits) * 3 + len(described)
        if hits or name_hits:
            ranked.append({"name": item["skill_name"], "description": item["description"],
                           "score": score, "matched": sorted(hits | name_hits), "origin": item["origin"]})
    return sorted(ranked, key=lambda entry: (-entry["score"], entry["name"]))[:3]


def token_comparison(selected: str | None) -> dict[str, Any]:
    rows = store.rows("SELECT * FROM ppa_skill_registry WHERE status='ACTIVE'")
    manifest_tokens = estimate_tokens(manifest_text())
    every_body = sum(estimate_tokens(item["body"]) for item in rows)
    one_body = next((estimate_tokens(item["body"]) for item in rows if item["skill_name"] == selected), 0)
    return {"manifests_only": manifest_tokens, "dump_everything": manifest_tokens + every_body,
            "progressive": manifest_tokens + one_body,
            "saved": every_body - one_body, "method": "estimated at four characters per token"}


def disclose(query: str) -> dict[str, Any]:
    """Retrieve manifests, then load only the top match."""
    matched = rank(query)
    selected = matched[0]["name"] if matched else None
    return {"query": query, "manifests": manifests(), "matched": matched,
            "disclosed_skill": load(selected) if selected else None,
            "token_comparison": token_comparison(selected),
            "retrieval": "keyword overlap with triggers (vector search over the registry in the notebook)",
            "sequence": ["retrieve compact manifests", "select the top approved match",
                         "load one full body"]}
