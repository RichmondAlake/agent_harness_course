"""Part 3: the context and cost ledger, trajectories, learning from them, and the scorecard."""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage

from conftest import Api

LAYERS = ["system prompt", "tool schemas", "now", "what you remember", "memories", "governed meanings",
          "skills", "request"]
REPLY = ["triage_inbox", "mail_send_message"]


def _senders(api: Api) -> list[dict]:
    """Rows of the practice inbox that can be answered, one for each sender."""
    seen: dict[str, dict] = {}
    for row in api.get("/api/inbox_triage/status")["rows"]:
        if row["category"] != "quarantine":
            seen.setdefault(row["from_name"], row)
    return list(seen.values())


def _reply(api: Api, row: dict, decision: str, note: str = "") -> dict:
    """One typed reply request, taken to the approval gate and decided."""
    paused = api.turn(f"Send a reply to {row['from_name']} on `{row['thread_id']}`.")
    assert paused["status"] == "awaiting_approval", paused
    resumed = api.post("/api/assistant/resume", {
        "thread_id": paused["thread_id"], "note": note,
        "decisions": {item["action_id"]: decision for item in paused["pending_actions"]}})
    assert resumed["status"] == "completed"
    return resumed


def _turn(api: Api, turn_id: str) -> dict:
    return api.get(f"/api/learning/trajectories/{turn_id}")


def _status(api: Api) -> dict:
    return api.get("/api/learning/status")


def _two_approved_replies(api: Api) -> list[str]:
    people = _senders(api)
    return [_reply(api, people[index], "approve")["run_id"] for index in (0, 1)]


def _draft(api: Api) -> dict:
    return api.post("/api/learning/draft", {"turn_ids": _two_approved_replies(api)})


def _gate(api: Api, name: str, version: int) -> dict:
    return api.post(f"/api/learning/skills/{name}/{version}/gate")


def _checks(gated: dict) -> dict[str, dict]:
    return {check["id"]: check for check in gated["gate"]["checks"]}


# ── The ledger ────────────────────────────────────────────────────────────────

def test_fresh_tokens_are_input_less_cache_reads_and_writes():
    from backend.core import ledger

    counts = ledger.split({"input_tokens": 1000, "cache_read_tokens": 600, "cache_write_tokens": 300,
                           "output_tokens": 50})
    assert counts == {"fresh": 100, "cache_write": 300, "cache_read": 600, "output": 50}
    # The Anthropic SDK reports fresh tokens directly, so nothing is taken away.
    raw = ledger.split({"input_tokens": 100, "cache_read_tokens": 600, "cache_write_tokens": 300,
                        "output_tokens": 50}, input_includes_cache=False)
    assert raw == counts
    assert ledger.split({"input_tokens": 10, "cache_read_tokens": 50})["fresh"] == 0, "never negative"


def test_cost_uses_the_four_prices_and_caching_saves_the_difference():
    from backend.core import ledger

    assert ledger.prices() == {"fresh": 4.0, "cache_write": 5.0, "cache_read": 0.2, "output": 20.0}
    counts = {"fresh": 100, "cache_write": 300, "cache_read": 600, "output": 50}
    assert ledger.cost(counts) == pytest.approx((100 * 4 + 300 * 5 + 600 * 0.2 + 50 * 20) / 1e6)
    assert ledger.cost({"fresh": 1_000_000}) == 4.0 and ledger.cost({"output": 1_000_000}) == 20.0
    assert ledger.saved_by_cache(1_000_000) == pytest.approx(4.0 - 0.2)
    assert ledger.saved_by_cache(0) == 0


def test_cache_writes_are_read_whichever_way_the_model_reports_them():
    from backend.core import llm_client

    single = AIMessage(content="", usage_metadata={
        "input_tokens": 900, "output_tokens": 10, "total_tokens": 910,
        "input_token_details": {"cache_read": 500, "cache_creation": 300}})
    assert llm_client.usage_of(single) == {"input_tokens": 900, "output_tokens": 10,
                                           "cache_read_tokens": 500, "cache_write_tokens": 300}
    split = AIMessage(content="", usage_metadata={
        "input_tokens": 900, "output_tokens": 10, "total_tokens": 910,
        "input_token_details": {"cache_read": 500, "cache_creation": 0, "ephemeral_5m_input_tokens": 300}})
    assert llm_client.usage_of(split)["cache_write_tokens"] == 300


def test_a_scripted_turn_is_a_zero_cost_row_with_real_context_layers(api: Api):
    done = api.turn("Prepare my morning brief.")
    seen = api.get("/api/context_cost/status")
    assert seen["model_called"] is False and seen["totals"]["all_scripted"] is True
    assert [layer["name"] for layer in seen["layers"]] == LAYERS
    assert {layer["name"] for layer in seen["layers"] if layer["stable"]} == {"system prompt", "tool schemas"}
    turn = next(item for item in seen["turns"] if item["turn_id"] == done["run_id"])
    assert list(turn["context_layers"]) == LAYERS and all(turn["context_layers"][name] > 0 for name in (
        "system prompt", "tool schemas", "now", "governed meanings", "skills", "request"))
    assert turn["context_tokens"] == sum(turn["context_layers"].values())
    assert turn["scripted"] and turn["usd"] == 0 and turn["model_calls"] == done["trace"]["model_calls"]
    detail = api.get(f"/api/context_cost/turn/{done['run_id']}")
    assert [call["step"] for call in detail["calls"]] == list(range(1, len(detail["calls"]) + 1))
    for call in detail["calls"]:
        assert call["note"] == "scripted responder, no model call" == seen["scripted_note"]
        assert call["fresh_tokens"] == call["cache_read_tokens"] == call["cache_write_tokens"] == 0
        assert call["output_tokens"] == 0 and call["usd"] == 0
    assert seen["totals"]["cache_read_share"] is None and seen["totals"]["saved_by_cache_usd"] == 0
    api.get("/api/context_cost/turn/no-such-turn", expect=404)


def test_a_model_call_is_priced_and_summed_by_turn(api: Api):
    from backend.core import ledger, trajectories

    trajectories.open_turn("turn-priced", "thread-priced", "A priced turn")
    ledger.record("turn-priced", 1, {"input_tokens": 12_000, "cache_write_tokens": 10_000,
                                     "cache_read_tokens": 0, "output_tokens": 400}, 2.5, scripted=False)
    ledger.record("turn-priced", 2, {"input_tokens": 13_000, "cache_write_tokens": 500,
                                     "cache_read_tokens": 10_000, "output_tokens": 300}, 1.5, scripted=False)
    total = api.get("/api/context_cost/turn/turn-priced")["totals"]
    assert (total["fresh_tokens"], total["cache_write_tokens"], total["cache_read_tokens"]) == (4500, 10_500, 10_000)
    assert total["input_tokens"] == 25_000 and total["output_tokens"] == 700 and total["seconds"] == 4.0
    assert total["usd"] == pytest.approx((4500 * 4 + 10_500 * 5 + 10_000 * 0.2 + 700 * 20) / 1e6)
    assert total["cache_read_share"] == 0.4
    assert total["saved_by_cache_usd"] == pytest.approx(10_000 * 3.8 / 1e6)
    seen = api.get("/api/context_cost/status")
    assert seen["totals"]["all_scripted"] is False and seen["turns"][-1]["cumulative_usd"] == total["usd"]


# ── Trajectories ──────────────────────────────────────────────────────────────

def test_a_turn_that_only_reads_is_answered(api: Api):
    done = api.turn("Prepare my morning brief.")
    turn = _turn(api, done["run_id"])
    assert turn["kind"] == "live" and turn["outcome"] == "answered" and turn["state"] == "closed"
    assert turn["request"] == "Prepare my morning brief." and turn["planned_by"] == "scripted responder"
    assert turn["skills"] == ["morning-brief"] and turn["owner_words"] == ""
    assert turn["tool_calls"][0] == "load_skill" and "triage_inbox" in turn["tool_calls"]
    assert "mail_send_message" in turn["tools_bound"] and turn["started_at"] <= turn["ended_at"]
    assert list(turn["context_layers"]) == LAYERS and turn["run"]["trigger"] == "chat"


def test_a_trajectory_survives_the_approval_pause_and_closes_as_approved(api: Api):
    row = _senders(api)[0]
    paused = api.turn(f"Send a reply to {row['from_name']} on `{row['thread_id']}`.")
    waiting = _turn(api, paused["run_id"])
    assert waiting["outcome"] is None and waiting["ended_at"] is None and waiting["state"] == "open"
    assert waiting["tool_calls"] == ["triage_inbox"], "what ran before the pause is already recorded"
    api.post("/api/assistant/resume", {"thread_id": paused["thread_id"], "decisions": {
        paused["pending_actions"][0]["action_id"]: "approve"}})
    closed = _turn(api, paused["run_id"])
    assert closed["outcome"] == "approved" and closed["tool_calls"] == REPLY and closed["skills"] == []
    assert closed["ended_at"] and [item["state"] for item in closed["actions"]] == ["EXECUTED"]


def test_a_declined_turn_keeps_the_owners_words(api: Api):
    declined = _reply(api, _senders(api)[0], "reject", "Not this week, I am away.")
    turn = _turn(api, declined["run_id"])
    assert turn["outcome"] == "declined" and turn["owner_words"] == "Not this week, I am away."
    assert turn["tool_calls"] == ["triage_inbox"], "a declined tool did not run"
    assert api.read("mail_list_sent")["sent"] == []
    assert _status(api)["corrections"][0]["owner_words"] == "Not this week, I am away."
    api.get("/api/learning/trajectories/no-such-turn", expect=404)


def test_outcomes_follow_the_decisions():
    from backend.core import trajectories

    yes, no = {"state": "EXECUTED", "decision_note": ""}, {"state": "REJECTED", "decision_note": "too soon"}
    assert trajectories.outcome_of([]) == ("answered", "")
    assert trajectories.outcome_of([yes, yes]) == ("approved", "")
    assert trajectories.outcome_of([no, no]) == ("declined", "too soon")
    assert trajectories.outcome_of([yes, no]) == ("mixed", "too soon")


# ── Workflow to skill ─────────────────────────────────────────────────────────

def test_a_workflow_must_repeat_with_no_skill_to_be_a_candidate(api: Api):
    people = _senders(api)
    api.turn("Prepare my morning brief.")
    api.turn("Prepare my morning brief.")                 # repeated, but with a skill
    api.turn("Remember that I prefer short replies.")     # only an always-bound helper tool
    api.turn("Remember that I like morning meetings.")
    first = _reply(api, people[0], "approve")
    assert _status(api)["candidates"] == [], "one turn is not a repeat"
    _reply(api, people[2], "reject", "Not now.")           # declined turns are not evidence
    assert _status(api)["candidates"] == []
    second = _reply(api, people[1], "approve")
    found = _status(api)["candidates"]
    assert len(found) == 1 and found[0]["signature"] == REPLY and found[0]["count"] == 2
    assert found[0]["turn_ids"] == [first["run_id"], second["run_id"]] and found[0]["drafted"] is None
    assert found[0]["outcomes"] == ["approved"]


def test_the_signature_ignores_helpers_and_repeats():
    from backend.core import learning

    assert learning.signature(["load_skill", "triage_inbox", "memory_search", "triage_inbox",
                               "mail_send_message"]) == REPLY
    assert learning.signature(["memory_write"]) == []


def test_the_sample_week_fills_the_chapter(api: Api):
    loaded = api.post("/api/learning/sample_week")
    assert [turn["outcome"] for turn in loaded["turns"]] == ["answered", "approved", "answered", "approved",
                                                             "declined"]
    assert all(turn["sample"] and turn["planned_by"] == "scripted responder" for turn in loaded["turns"])
    seen = _status(api)
    assert seen["counts"]["turns"] == 5 and seen["counts"]["live"] == 5 and seen["counts"]["replay"] == 0
    assert [item["signature"] for item in seen["candidates"]] == [REPLY] and seen["candidates"][0]["sample"]
    assert [item["owner_words"] for item in seen["corrections"]] == [
        "Always check my calendar before you offer a time in a reply."]
    assert [item["id"] for item in seen["gate"]] == ["real_tools", "no_regression", "held_out",
                                                     "approval_contract", "replay"]
    assert len(seen["frozen"]) == 10 and set(seen["destinations"]) == {"procedure", "preference", "one_off"}
    assert seen["written_by"].startswith("A template") and seen["routed_by"].startswith("A written rule")
    api.post("/api/reset", {"confirm": "reset"})
    assert _status(api)["counts"]["turns"] == 0, "Reset removes the practice data"


def test_a_drafted_skill_is_a_candidate_and_is_not_offered(api: Api):
    drafted = _draft(api)
    assert drafted["version"] == 1 and drafted["state"] == "CANDIDATE" and drafted["origin"] == "learned"
    assert drafted["skill_name"] == "learned-mail-send-message"
    assert drafted["evidence"]["signature"] == REPLY and len(drafted["evidence"]["turn_ids"]) == 2
    assert drafted["evidence"]["templated"] is True and "template" in drafted["drafted_by"]
    assert len(drafted["evidence"]["held_out"]) == 3
    assert not set(drafted["evidence"]["held_out"]) & set(drafted["evidence"]["requests"])
    assert "`triage_inbox`" in drafted["body"] and "`mail_send_message`" in drafted["body"]
    assert "approval" in drafted["body"] and len(drafted["body_sha256"]) == 64
    assert drafted["skill_name"] not in [item["name"] for item in api.get("/api/skills/status")["manifests"]]
    listed = next(item for item in _status(api)["skills"] if item["name"] == drafted["skill_name"])
    assert listed["live_version"] is None and listed["versions"][0]["status"] == "CANDIDATE"
    assert _status(api)["candidates"][0]["drafted"] == {
        "name": drafted["skill_name"], "version": 1, "state": "CANDIDATE", "live": False}


def test_a_draft_needs_real_evidence(api: Api):
    brief = api.turn("Prepare my morning brief.")["run_id"]
    reply = _reply(api, _senders(api)[0], "approve")["run_id"]
    api.post("/api/learning/draft", {"turn_ids": [brief, reply]}, expect=400)      # one used a skill
    api.post("/api/learning/draft", {"turn_ids": [reply, "no-such-turn"]}, expect=400)
    api.post("/api/learning/draft", {"turn_ids": [reply]}, expect=422)


# ── The gate ──────────────────────────────────────────────────────────────────

def test_the_gate_passes_a_good_candidate_and_sends_nothing(api: Api):
    drafted = _draft(api)
    name = drafted["skill_name"]
    sent_before = len(api.read("mail_list_sent")["sent"])
    gated = _gate(api, name, 1)
    checks = _checks(gated)
    assert list(checks) == ["real_tools", "no_regression", "held_out", "approval_contract", "replay"]
    assert all(check["passed"] for check in checks.values()), {key: item["detail"] for key, item in checks.items()}
    assert gated["state"] == "PASSED" and gated["gate"]["passed"] and gated["gate"]["failing"] == []
    replay = checks["replay"]
    assert replay["paused_on"] == ["mail_send_message"] and replay["outcome"] == "declined"
    assert replay["request"] == drafted["evidence"]["held_out"][0]
    turn = _turn(api, replay["turn_id"])
    assert turn["kind"] == "replay" and turn["owner_words"] == "gate replay" and turn["skills"] == [name]
    assert [item["state"] for item in turn["actions"]] == ["REJECTED"]
    assert len(api.read("mail_list_sent")["sent"]) == sent_before, "a replay sends nothing"
    # The trial put the pointer back: the candidate is stored, passed, and still not live.
    seen = _status(api)
    assert next(item for item in seen["skills"] if item["name"] == name)["live_version"] is None
    assert [row["action"] for row in seen["log"] if row["skill_name"] == name] == ["restore", "trial"]
    assert seen["candidates"][0]["count"] == 2, "a replay is never evidence"
    report = gated["gate"]["cost_report"]
    assert report["replay"]["model_calls"] >= 1 and report["earlier_turns_without_the_skill"]["turns"] == 2
    assert "does not gate" in report["note"]


def test_the_gate_publishes_each_check_as_it_finishes(api: Api):
    from backend.core.events import bus

    drafted = _draft(api)
    _gate(api, drafted["skill_name"], 1)
    events = [item["data"] for item in reversed(bus.recent("gate", 20))]
    assert [item["status"] for item in events] == ["started", *["check"] * 5, "finished"]
    assert [item["position"] for item in events[1:6]] == [1, 2, 3, 4, 5] and events[-1]["passed"] is True


def _candidate(api: Api, name: str, *, body: str, triggers: list[str], held_out: list[str],
               signature: list[str] | None = None) -> dict:
    from backend.core import skills

    skills.write_version(name, f"A test candidate called {name}.", triggers, body, origin="learned",
                         evidence={"turn_ids": [], "signature": signature or [], "requests": [],
                                   "held_out": held_out})
    return _checks(_gate(api, name, 1))


def test_a_procedure_that_names_no_real_tool_fails(api: Api):
    unknown = _candidate(api, "zebra-one", body="1. Call `mail_delete_everything`.", triggers=["zebra"],
                         held_out=["Zebra this, please."])
    assert not unknown["real_tools"]["passed"] and "mail_delete_everything" in unknown["real_tools"]["detail"]
    nothing = _candidate(api, "zebra-two", body="1. Think about it.", triggers=["zebra"],
                         held_out=["Zebra that, please."])
    assert not nothing["real_tools"]["passed"] and "names no tool" in nothing["real_tools"]["detail"]
    hidden = _candidate(api, "zebra-three", body="1. Call `focus_session_report`.", triggers=["zebra"],
                        held_out=["Zebra more, please."])
    assert not hidden["real_tools"]["passed"], "a tool reserved for the harness is not one the model can call"


def test_a_candidate_that_takes_over_a_frozen_request_fails(api: Api):
    checks = _candidate(api, "grab-the-brief", body="1. Call `week_load`.",
                        triggers=["prepare", "morning", "brief", "my"], held_out=["Prepare my morning brief now."])
    assert not checks["no_regression"]["passed"]
    assert "Prepare my morning brief." in checks["no_regression"]["detail"]
    stored = next(item for item in _status(api)["skills"] if item["name"] == "grab-the-brief")
    assert stored["live_version"] is None and stored["versions"][0]["state"] == "FAILED"
    assert stored["versions"][0]["status"] == "CANDIDATE", "a failed version stays a candidate"
    assert "No regression on the frozen ten" in stored["versions"][0]["gate"]["failing"]
    api.post("/api/learning/skills/grab-the-brief/1/promote", expect=409)


def test_a_candidate_may_claim_a_frozen_request_of_its_own_kind(api: Api):
    from backend.core import learning

    own = next(case for case in learning.FROZEN if case.get("tools") == ["task_add"])
    assert learning._own_kind(own, "learned-task-add", ["task_add"])
    assert not learning._own_kind(own, "learned-task-add", ["task_add", "mail_send_message"])
    assert not learning._own_kind(learning.FROZEN[0], "learned-task-add", ["task_add"])
    assert learning._own_kind(learning.FROZEN[0], "morning-brief", [])
    checks = _candidate(api, "learned-adding", body="1. Call `task_add`. Give the reason.",
                        triggers=["add"], held_out=["Add a task: water the plants, please."],
                        signature=["task_add"])
    assert checks["no_regression"]["passed"], checks["no_regression"]["detail"]
    assert checks["replay"]["passed"] and checks["replay"]["paused_on"] == ["task_add"]
    assert api.get("/api/assistant/tasks")["open"] == [], "the replay declined its own write"


def test_held_out_phrasings_must_reach_the_candidate(api: Api):
    missed = _candidate(api, "zebra-route", body="1. Call `week_load`.", triggers=["zebra"],
                        held_out=["Tell me something else, please."])
    assert not missed["held_out"]["passed"] and "went to no skill" in missed["held_out"]["detail"]
    empty = _candidate(api, "zebra-none", body="1. Call `week_load`.", triggers=["zebra"], held_out=[])
    assert not empty["held_out"]["passed"] and not empty["replay"]["passed"]


def test_a_held_out_phrasing_cannot_be_evidence():
    from backend.core import learning

    reused = learning.check_held_out("anything", ["Send a  reply to Ann."], ["send a reply to ann."])
    assert not reused["passed"] and "not held out" in reused["detail"]


def test_a_procedure_cannot_waive_approval(api: Api):
    checks = _candidate(api, "zebra-waiver", body="1. Call `mail_send_message` without asking the owner.",
                        triggers=["zebra"], held_out=["Zebra the mail, please."])
    assert not checks["approval_contract"]["passed"] and "without asking" in checks["approval_contract"]["detail"]
    kept = _candidate(api, "zebra-keeper", body="1. Call `week_load`.", triggers=["zebra"],
                      held_out=["Zebra the week, please."])
    assert kept["approval_contract"]["passed"] and "approval_required" in kept["approval_contract"]["detail"]


def test_a_replay_that_does_not_follow_the_procedure_fails(api: Api):
    idle = _candidate(api, "zebra-idle", body="1. Call `week_load`.", triggers=["zebra"],
                      held_out=["Zebra everything, please."])
    assert idle["held_out"]["passed"] and not idle["replay"]["passed"]
    assert "none of the tools" in idle["replay"]["detail"]
    never = _candidate(api, "zebra-writer", body="1. Call `mail_send_message`.", triggers=["zebra"],
                       held_out=["Zebra a letter, please."], signature=["mail_send_message"])
    assert not never["replay"]["passed"] and "never reached the approval gate" in never["replay"]["detail"]


# ── Promote, refine, roll back ────────────────────────────────────────────────

def test_promote_then_refine_then_roll_back(api: Api):
    drafted = _draft(api)
    name = drafted["skill_name"]
    api.post(f"/api/learning/skills/{name}/1/promote", expect=409)       # the gate has not run
    _gate(api, name, 1)
    assert api.post(f"/api/learning/skills/{name}/1/promote")["live"] is True
    assert name in [item["name"] for item in api.get("/api/skills/status")["manifests"]]
    live = next(item for item in api.get("/api/skills/status")["live"] if item["name"] == name)
    assert live["version"] == 1 and live["origin"] == "learned"
    # A later request of the same kind now loads the skill, so it is no longer new evidence.
    again = _reply(api, _senders(api)[2], "approve")
    assert _turn(api, again["run_id"])["skills"] == [name]
    assert _status(api)["candidates"][0]["count"] == 2

    lesson = "Always check my calendar before you offer a time in a reply."
    refined = api.post(f"/api/learning/skills/{name}/refine", {"correction": lesson, "turn_id": again["run_id"]})
    assert refined["version"] == 2 and refined["state"] == "CANDIDATE" and refined["origin"] == "refined"
    assert refined["body"].endswith(f"Corrections from the owner\n- {lesson}") and refined["evidence"]["correction"] == lesson
    assert refined["evidence"]["refines"] == 1 and refined["evidence"]["turn_ids"] == [again["run_id"]]
    assert next(item for item in api.get("/api/skills/status")["live"] if item["name"] == name)["version"] == 1

    difference = api.get(f"/api/learning/skills/{name}/diff?a=1&b=2")
    assert [line["text"] for line in difference["lines"] if line["kind"] == "added"] == ["", "Corrections from the owner", f"- {lesson}"]
    assert not [line for line in difference["lines"] if line["kind"] == "removed"]
    assert api.get(f"/api/learning/skills/{name}/diff?a=1&b=1")["identical"] is True

    gated = _gate(api, name, 2)
    assert gated["state"] == "PASSED", gated["gate"]["failing"]
    api.post(f"/api/learning/skills/{name}/2/promote")
    assert api.get(f"/api/skills/{name}")["version"] == 2 and lesson in api.get(f"/api/skills/{name}")["body"]

    back = api.post(f"/api/learning/skills/{name}/activate", {"version": 1, "reason": "the lesson was wrong"})
    assert back["live"] is True and api.get(f"/api/skills/{name}")["version"] == 1
    seen = _status(api)
    listed = next(item for item in seen["skills"] if item["name"] == name)
    assert listed["live_version"] == 1 and [v["version"] for v in listed["versions"]] == [2, 1]
    assert {v["version"]: v["status"] for v in listed["versions"]} == {1: "ACTIVE", 2: "RETIRED"}
    newest = [row for row in seen["log"] if row["skill_name"] == name][0]
    assert (newest["action"], newest["version"], newest["reason"]) == ("activate", 1, "the lesson was wrong")
    api.post(f"/api/learning/skills/{name}/activate", {"version": 9}, expect=404)

    api.post(f"/api/learning/skills/{name}/retire", {"reason": "no longer wanted"})
    assert name not in [item["name"] for item in api.get("/api/skills/status")["manifests"]]
    assert len(next(item for item in _status(api)["skills"] if item["name"] == name)["versions"]) == 2
    api.post(f"/api/learning/skills/{name}/retire", {}, expect=404)


def test_an_authored_skill_can_be_refined_through_the_same_gate(api: Api):
    assert api.get("/api/skills/weekly-review")["version"] == 1
    refined = api.post("/api/learning/skills/weekly-review/refine", {"correction": "Always name the day I slipped most"})
    assert refined["version"] == 2 and refined["origin"] == "refined"
    assert refined["evidence"]["held_out"][0] == "Run my weekly review, please."
    gated = _gate(api, "weekly-review", 2)
    assert gated["state"] == "PASSED", {key: item["detail"] for key, item in _checks(gated).items()}
    assert api.get("/api/skills/weekly-review")["version"] == 1, "passing the gate is not promotion"
    api.post("/api/learning/skills/no-such-skill/refine", {"correction": "anything"}, expect=404)


def test_a_trial_cut_short_is_undone_at_start_up(api: Api):
    from backend.core import skills, store

    skills.write_version("weekly-review", "Changed.", ["weekly"], "1. Call `weekly_review_data`.", origin="refined")
    store.set_meta(skills.TRIAL_KEY, store.dumps({"name": "weekly-review", "before": 1}))
    skills.activate("weekly-review", 2, "gate trial", action="trial")      # as if the process stopped here
    skills.sync_registry()
    assert skills.live_versions()["weekly-review"] == 1 and store.get_meta(skills.TRIAL_KEY) is None


# ── Corrections ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,destination", [
    ("Always check my calendar before you offer a time in a reply.", "procedure"),
    ("Never send on a Friday afternoon.", "procedure"),
    ("I prefer short replies.", "preference"),
    ("I always prefer a phone call.", "preference"),
    ("Not now, I am in a meeting.", "one_off"),
    ("Wrong person.", "one_off"),
    ("Hmm.", "one_off"),
])
def test_the_fallback_rule_routes_a_correction(text: str, destination: str):
    from backend.core import learning

    assert learning.route_by_rule(text)[0] == destination
    routed = learning.route_lesson(text)
    assert routed["destination"] == destination and routed["by"] == "rule" and routed["probabilities"] is None
    assert set(routed["destinations"]) == {"procedure", "preference", "one_off"}


def test_a_routed_correction_reaches_its_destination(api: Api):
    assert api.post("/api/learning/correction/route", {"text": "I prefer short replies."})["destination"] == "preference"
    api.post("/api/learning/correction/route", {"text": ""}, expect=422)
    saved = api.post("/api/learning/correction/apply", {"text": "I prefer short replies.", "destination": "preference"})
    assert saved["memory"]["memory_type"] == "preference" and saved["memory"]["content"] == "I prefer short replies."
    nothing = api.post("/api/learning/correction/apply", {"text": "Not now.", "destination": "one_off"})
    assert nothing["note"] == "Nothing was changed."
    api.post("/api/learning/correction/apply", {"text": "Always check.", "destination": "procedure"}, expect=400)
    written = api.post("/api/learning/correction/apply", {
        "text": "Always name the day I slipped most.", "destination": "procedure", "skill": "weekly-review"})
    assert (written["skill"], written["version"], written["state"]) == ("weekly-review", 2, "CANDIDATE")


# ── The scorecard ─────────────────────────────────────────────────────────────

def test_the_scorecard_is_ready_on_honest_work(api: Api):
    fresh = api.get("/api/scorecard/status")
    assert fresh["verdict"] == "READY" and fresh["failing"] == []
    assert [check["id"] for check in fresh["checks"]] == [
        "attacks_obeyed", "unapproved_outward", "tasks_from_quarantine", "procedure_selection", "audit_complete",
        "duplicate_tasks", "cache_read_share", "median_turn_seconds", "cost_per_turn"]
    assert fresh["blocking_checks"] == 6 and fresh["reported"] == 3 and fresh["quarantined_threads"] > 0
    for check in fresh["checks"]:
        assert check["explains"].endswith(".") and check["evidence"] and check["threshold"]
        assert check["status"] == ("pass" if check["blocking"] else "reported")
    api.post("/api/learning/sample_week")
    api.turn("Triage my inbox and turn anything actionable into tasks.")
    api.turn("Triage my inbox and turn anything actionable into tasks.")
    worked = api.get("/api/scorecard/status")
    assert worked["verdict"] == "READY", worked["failing"]
    by_id = {check["id"]: check for check in worked["checks"]}
    assert by_id["procedure_selection"]["value"] == "10 of 10"
    done, of = by_id["audit_complete"]["value"].split(" of ")
    assert done == of and int(of) > 0
    assert "no model was called" in by_id["cache_read_share"]["detail"] and by_id["cost_per_turn"]["value"] == 0


def test_the_scorecard_blocks_and_names_what_failed(api: Api):
    from backend.core import store

    stamp = store.real_now()
    store.execute(
        "INSERT INTO ppa_action_audit(action_id,run_id,thread_id,session_id,origin,tool_name,tier,summary,"
        "reason,payload,state,created_at,executed_at,real_created_at) VALUES (?,?,?,?,?,?,'approval',?,?,?,"
        "'EXECUTED',?,?,?)", ("ACT-ROGUE", None, "t", "s", "agent", "mail_send_message", "Send mail", "",
                              "{}", stamp, stamp, stamp))
    for task in ("T-ONE", "T-TWO"):
        store.execute("INSERT INTO ppa_tasks(task_id,title,source_type,source_ref,content_hash,created_at,"
                      "touched_at) VALUES (?,?,?,?,?,?,?)", (task, "Twice", "mail", "thr-same", task, stamp, stamp))
    blocked = api.get("/api/scorecard/status")
    assert blocked["verdict"] == "BLOCKED"
    assert "Outward actions executed without approval" in blocked["failing"]
    assert "Duplicate tasks per source" in blocked["failing"]
    by_id = {check["id"]: check for check in blocked["checks"]}
    assert by_id["unapproved_outward"]["value"] == 1 and "ACT-ROGUE" in by_id["unapproved_outward"]["detail"]
    assert by_id["duplicate_tasks"]["value"] == 1 and by_id["attacks_obeyed"]["passed"]


def test_quarantine_and_selection_can_block(api: Api):
    from backend.core import scorecard, skills, store

    held = next(row["thread_id"] for row in api.get("/api/inbox_triage/status")["rows"]
                if row["category"] == "quarantine")
    stamp = store.real_now()
    store.execute("INSERT INTO ppa_tasks(task_id,title,source_type,source_ref,content_hash,created_at,"
                  "touched_at) VALUES (?,?,?,?,?,?,?)", ("T-BAD", "Planted", "mail", held, "h", stamp, stamp))
    skills.retire("weekly-review", "to break the frozen ten")
    blocked = api.get("/api/scorecard/status")
    assert {"Tasks created from quarantined mail", "Procedure selection on the frozen ten"} <= set(blocked["failing"])
    assert next(check for check in blocked["checks"] if check["id"] == "procedure_selection")["value"] == "9 of 10"
    passing = [{"title": "a", "blocking": True, "passed": True}, {"title": "b", "blocking": False, "passed": None}]
    assert scorecard.verdict(passing)["verdict"] == "READY"
    assert scorecard.verdict([*passing, {"title": "c", "blocking": True, "passed": False}]) == {
        "verdict": "BLOCKED", "failing": ["c"], "blocking_checks": 2, "passed": 1, "reported": 1}


# ── Caching in the Claude path, checked without calling Claude ────────────────

def test_the_claude_call_caches_the_system_prompt_and_the_conversation(monkeypatch):
    from backend.core import llm_client

    sent: dict = {}

    class Bound:
        async def ainvoke(self, messages, **kwargs):
            sent.update(messages=messages, kwargs=kwargs)
            return AIMessage(content="ok", response_metadata={"stop_reason": "end_turn"})

    monkeypatch.setattr(llm_client, "_claude", lambda: Bound())
    asyncio.run(llm_client.respond("claude", "The frozen system prompt.", []))
    block = sent["messages"][0].content[-1]
    assert block == {"type": "text", "text": "The frozen system prompt.", "cache_control": {"type": "ephemeral"}}
    assert sent["kwargs"] == {"cache_control": {"type": "ephemeral"}}
