"""System One: what the harness does with a probability, and what it does without one.

No test calls the service. A stand-in answers in its place, so that the rules around the
answer are what is tested: the threshold, the quarantine rule, the fallback and the log.
"""
from __future__ import annotations

import httpx
import pytest

from backend.core import system_one
from conftest import Api


class Answer:
    """What the service would send back for a request."""

    def __init__(self, body: dict):
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


def stand_in(monkeypatch, reply):
    """Switch System One on and answer every request with ``reply(questions, state)``."""
    asked = []

    def post(url, **kwargs):
        asked.append(kwargs["json"])
        return Answer({"answers": reply(kwargs["json"]["questions"], kwargs["json"]["state"]),
                       "usage": {"input_tokens": 100, "output_tokens": 0}})

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")
    monkeypatch.setattr(httpx, "post", post)
    system_one.forget()
    return asked


def test_without_a_key_rules_decide_and_nothing_is_sent(api: Api, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("nothing may be sent when System One is off"))
    state = api.get("/api/system_one/status")
    assert not state["available"] and not state["configured"] and "off" in state["label"]
    lab = api.post("/api/system_one/attack_lab")
    assert lab["note"] and lab["flagged_by_system_one"] == 0
    assert lab["flagged_by_tripwire"] >= 1, "the tripwire still screens the inbox"
    assert system_one.rerank("anything", {"a": "one", "b": "two", "c": "three", "d": "four"})["kept"] == ["a", "b", "c"]
    assert system_one.select("anything", {"s": "a skill"}, {"t": "a tool"}) is None


def test_the_key_is_never_returned(api: Api, monkeypatch):
    stand_in(monkeypatch, lambda questions, state: {})
    shown = str(api.get("/api/system_one/status")) + str(api.get("/api/architecture"))
    assert "test-key-not-real" not in shown


def test_a_flagged_message_from_a_stranger_is_quarantined(api: Api, monkeypatch):
    before = {row["thread_id"]: row for row in api.get("/api/inbox_triage/status")["rows"]}
    missed = [row for row in before.values()
              if row["trust"] == "unknown" and row["category"] != "quarantine"]
    known = next(row for row in before.values() if row["trust"] != "unknown")

    def reply(questions, state):      # every message is judged an attack
        return {name: {"type": "noul", "noul": 0.93} for name in questions}

    stand_in(monkeypatch, reply)
    after = {row["thread_id"]: row for row in api.get("/api/inbox_triage/status")["rows"]}
    for row in missed:
        assert after[row["thread_id"]]["category"] == "quarantine", "a stranger's flagged mail is held"
        assert "system one" in after[row["thread_id"]]["detectors"]
    assert after[known["thread_id"]]["category"] == known["category"], "a known person's mail stays"
    assert after[known["thread_id"]]["flagged_by_system_one"], "and it is marked"


def test_the_threshold_belongs_to_the_harness(api: Api, monkeypatch):
    def reply(questions, state):
        return {name: {"type": "noul", "noul": system_one.ATTACK_THRESHOLD - 0.01} for name in questions}

    stand_in(monkeypatch, reply)
    lab = api.post("/api/system_one/attack_lab")
    assert lab["flagged_by_system_one"] == 0, "just under the threshold is not flagged"


def test_reranking_keeps_the_useful_few_or_nothing(api: Api, monkeypatch):
    candidates = {"a": "one", "b": "two", "c": "three", "d": "four"}
    shares = {"a": 0.05, "b": 0.45, "c": 0.30, "d": 0.10, "none": 0.10}
    stand_in(monkeypatch, lambda questions, state: {"pick": {"type": "choice", "probabilities": shares}})
    assert system_one.rerank("q", candidates)["kept"] == ["b", "c"], "a third of the best, best first"
    noise = {"a": 0.1, "b": 0.1, "c": 0.1, "d": 0.1, "none": 0.6}
    stand_in(monkeypatch, lambda questions, state: {"pick": {"type": "choice", "probabilities": noise}})
    assert system_one.rerank("q", candidates)["kept"] == [], "none took half: keep nothing"


def test_one_request_chooses_procedures_and_tools(api: Api, monkeypatch):
    def reply(questions, state):
        answers = {name: {"type": "noul", "noul": 0.9 if name == "focus_start" else 0.1}
                   for name in questions if name != "procedure"}
        answers["procedure"] = {"type": "choice", "probabilities": {"focus": 0.7, "brief": 0.28, "none": 0.02}}
        return answers

    asked = stand_in(monkeypatch, reply)
    chosen = system_one.select("Start a Pomodoro", {"focus": "focus", "brief": "brief"},
                               {"focus_start": "start", "mail_send": "send"})
    assert chosen["skills"] == ["focus", "brief"] and chosen["tools"] == ["focus_start"]
    assert len(asked) == 1, "one request carries every question"


def test_a_failure_falls_back_and_is_logged(api: Api, monkeypatch):
    def fail(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")
    monkeypatch.setattr(httpx, "post", fail)
    system_one.forget()
    assert system_one.rerank("q", {"a": "one", "b": "two"})["by"] == "the order of the search"
    logged = api.get("/api/system_one/decisions")["decisions"]
    assert logged and logged[0]["outcome"] == "ConnectError" and logged[0]["kind"] == "rerank"
    assert api.get("/api/inbox_triage/status")["rows"], "triage still answers"
