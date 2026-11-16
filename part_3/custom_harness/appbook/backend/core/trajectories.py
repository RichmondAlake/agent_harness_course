"""Trajectories: one row for each turn, written as the turn happens.

A trajectory is the record of how one request was handled: what was asked,
what the harness offered, which tools ran in which order, and how it ended.
``ppa_turns`` holds it. The row is written when the turn starts, filled in
when the context is assembled, updated when the run pauses for approval, and
closed when the turn ends. Because it is a row in the store and not a value
in memory, it is still there after a restart, while a run waits for a
decision.

``outcome`` is the signal that later chapters read.

* ``answered``: the turn only read. Nothing was put to the owner.
* ``approved``: every action put to the owner was approved.
* ``declined``: every action put to the owner was declined.
* ``mixed``: some were approved and some declined.

``kind`` is ``live`` for a real turn and ``replay`` for a turn the promotion
gate ran to test a skill. A replay never counts as evidence.
"""
from __future__ import annotations

from typing import Any

from backend.core import store

KINDS = ("live", "replay")
OUTCOMES = ("answered", "approved", "declined", "mixed")
SAMPLE_PREFIX = "sample-week-"          # threads the sample week runs on, so the page can label them


def open_turn(turn_id: str, thread_id: str, request: str, *, kind: str = "live", planned_by: str = "",
              tools_bound: list[str] | None = None) -> None:
    """The turn has started. Everything else is filled in as it happens."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    store.execute(
        "INSERT INTO ppa_turns(turn_id,thread_id,kind,request,planned_by,skills,tools_bound,context_layers,"
        "tool_calls,owner_words,started_at) VALUES (?,?,?,?,?,'[]',?,'{}','[]','',?)",
        (turn_id, thread_id, kind, request, planned_by, store.dumps(tools_bound or []), store.real_now()))


def plan(turn_id: str, context_layers: dict[str, int]) -> None:
    """The context is assembled: record the size of each layer."""
    store.execute("UPDATE ppa_turns SET context_layers=? WHERE turn_id=?",
                  (store.dumps(context_layers), turn_id))


def progress(turn_id: str, tool_calls: list[str], skills: list[str]) -> None:
    """What has run so far. Written when a run pauses, so the pause loses nothing."""
    store.execute("UPDATE ppa_turns SET tool_calls=?,skills=? WHERE turn_id=?",
                  (store.dumps(tool_calls), store.dumps(skills), turn_id))


def outcome_of(decisions: list[dict[str, Any]]) -> tuple[str, str]:
    """The outcome of a turn from the decisions on its gated actions, and the owner's words."""
    approved = [item for item in decisions if item["state"] in ("APPROVED", "EXECUTED", "FAILED")]
    declined = [item for item in decisions if item["state"] == "REJECTED"]
    words = "; ".join(dict.fromkeys(item["decision_note"].strip() for item in declined
                                    if (item.get("decision_note") or "").strip()))
    if not approved and not declined:
        return "answered", ""
    if approved and declined:
        return "mixed", words
    return ("approved", "") if approved else ("declined", words)


def close(turn_id: str, tool_calls: list[str], skills: list[str]) -> dict[str, Any] | None:
    """The turn has ended: record what ran and how the owner decided."""
    decisions = store.rows("SELECT state,decision_note FROM ppa_action_audit WHERE run_id=? AND tier='approval' "
                           "ORDER BY rowid", (turn_id,))
    outcome, words = outcome_of(decisions)
    store.execute("UPDATE ppa_turns SET tool_calls=?,skills=?,outcome=?,owner_words=?,ended_at=? WHERE turn_id=?",
                  (store.dumps(tool_calls), store.dumps(skills), outcome, words, store.real_now(), turn_id))
    return get(turn_id)


def fail(turn_id: str) -> None:
    """The turn stopped on an error. It has an end and no outcome."""
    store.execute("UPDATE ppa_turns SET ended_at=? WHERE turn_id=?", (store.real_now(), turn_id))


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "skills": store.loads(item["skills"], []), "tools_bound": store.loads(item["tools_bound"], []),
            "context_layers": store.loads(item["context_layers"], {}),
            "tool_calls": store.loads(item["tool_calls"], []),
            "sample": item["thread_id"].startswith(SAMPLE_PREFIX),
            "state": "closed" if item["outcome"] else ("did not finish" if item["ended_at"] else "open")}


def get(turn_id: str) -> dict[str, Any] | None:
    found = store.row("SELECT * FROM ppa_turns WHERE turn_id=?", (turn_id,))
    return _shape(found) if found else None


def recent(limit: int = 60, *, kind: str | None = None) -> list[dict[str, Any]]:
    found = store.rows("SELECT * FROM ppa_turns ORDER BY rowid DESC LIMIT ?", (limit,))
    return [_shape(item) for item in found if kind is None or item["kind"] == kind]


def every() -> list[dict[str, Any]]:
    """All turns, oldest first."""
    return [_shape(item) for item in store.rows("SELECT * FROM ppa_turns ORDER BY rowid")]


def detail(turn_id: str) -> dict[str, Any] | None:
    """One trajectory with the actions that were put to the owner during it."""
    found = get(turn_id)
    if found is None:
        return None
    actions = store.rows("SELECT action_id,tool_name,tier,summary,state,delivery,decision_note FROM "
                         "ppa_action_audit WHERE run_id=? ORDER BY rowid", (turn_id,))
    run = store.row("SELECT trigger,responder,status,answer FROM ppa_agent_runs WHERE run_id=?", (turn_id,))
    return {**found, "actions": actions, "run": run}


def counts() -> dict[str, int]:
    found = every()
    tally = {"turns": len(found), "live": 0, "replay": 0, "open": 0}
    for item in found:
        tally[item["kind"]] += 1
        tally["open"] += item["state"] == "open"
        if item["outcome"]:
            tally[item["outcome"]] = tally.get(item["outcome"], 0) + 1
    return tally
