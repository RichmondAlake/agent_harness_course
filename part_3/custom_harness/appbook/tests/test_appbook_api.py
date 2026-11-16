"""Offline tests for the PPA appbook, through its HTTP API.

The practice workspace is a real mailbox, so no test names a thread, a person
or an event. Each test states a rule and checks it against whatever the
workspace holds, using the shared policy as the reference.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from conftest import STORE, Api, minutes, policy
from world import build_world


def _actionable(api: Api) -> dict:
    """A thread the policy says needs an answer from the owner."""
    rows = api.get("/api/inbox_triage/status")["rows"]
    return next(row for row in rows if row["category"] in ("reply", "task"))


def _overlaps(start: str, end: str, events: list[dict]) -> list[str]:
    begin, finish = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return [item["event_id"] for item in events
            if datetime.fromisoformat(item["start"]) < finish and datetime.fromisoformat(item["end"]) > begin]


# ── Honesty ──────────────────────────────────────────────────────────────────

def test_the_status_says_what_is_really_running(api: Api):
    status = api.get("/api/status")
    assert status["ready"] and status["workspace"]["practice"] and status["workspace"]["safe_mode"]
    assert status["substrate"] == STORE, "one place names the store"
    assert status["responder"]["label"] == "scripted responder"
    assert status["clock"]["mode"] == "practice" and not status["clock"]["ticking"]
    assert status["workspace"]["provenance"]["owner_email"] == status["owner"]["email"]


def test_harness_owned_state_starts_empty(api: Api):
    tables = {item["name"]: item["row_count"] for item in api.get("/api/data_explorer/tables")["tables"]}
    for name in ("ppa_tasks", "ppa_focus_sessions", "ppa_memories", "ppa_action_audit",
                 "ppa_notifications", "ppa_agent_runs", "ppa_scratch_files"):
        assert tables[name] == 0, f"{name} should start empty"
    assert tables["ppa_contacts"] > 0 and tables["ppa_skill_registry"] == 7
    review = api.get("/api/weekly_review/status")["review"]
    assert review["empty"] and review["time_by_task"] == [] and review["slipping"] == []


def test_the_ledger_admits_what_is_missing(api: Api):
    ledger = {item["concern"]: item["status"] for item in api.get("/api/architecture")["ledger"]}
    assert ledger["Semantic cache"] == "not-implemented-by-design"
    assert ledger["Multi-agent orchestration"] == "missing"
    assert ledger["System One model"] == "partial", "it screens and ranks; it does not choose the tools"
    assert ledger["Database substrate"].startswith("partial")
    assert ledger["Embedding model"].startswith("partial")
    assert ledger["Model adapter"] == "built-inactive-no-key"


# ── Systems of record ────────────────────────────────────────────────────────

def test_tools_off_the_allowlist_cannot_be_reached(api: Api):
    status = api.get("/api/systems_of_record/status")
    offered = [tool for tools in status["servers"].values() for tool in tools]
    hidden = [tool["name"] for tool in offered if not tool["exposed"]]
    assert hidden and hidden == status["never_exposed"]
    assert all(tool["tier"] == "never" for tool in offered if not tool["exposed"])
    thread = _actionable(api)["thread_id"]
    for name in hidden:
        arguments = {"thread_id": thread} if name.startswith("mail") else \
            {"event_id": "x"} if name.startswith("calendar") else {"page_id": "x", "email": "a@b.example"}
        if name == "notes_delete_page":
            arguments = {"page_id": "x"}
        attempt = api.post("/api/systems_of_record/attempt", {"name": name, "arguments": arguments})
        assert attempt["offered_by_server"] and not attempt["reached"]
    assert api.get("/api/systems_of_record/effects")["effects"] == []
    assert api.read("mail_get_thread", thread_id=thread).get("thread"), "the thread is still there"


def test_external_text_reaches_the_model_delimited(api: Api):
    thread = _actionable(api)["thread_id"]
    read = api.post("/api/systems_of_record/read", {"name": "mail_get_thread",
                                                    "arguments": {"thread_id": thread}})
    body = read["raw_mcp_result"]["thread"]["body"]
    shown = read["model_facing_result"]
    assert "body" not in shown and shown["content"].startswith("<untrusted_content")
    assert shown["content"].count("</untrusted_content>") == 1 and body[:40] in shown["content"]


# ── Triage ───────────────────────────────────────────────────────────────────

def test_triage_matches_the_policy_and_leads_with_the_lowest_rank(api: Api):
    rows = api.get("/api/inbox_triage/status")["rows"]
    world = build_world()
    expected = policy.triage_signals(world["emails"], world["contacts"], [],
                                     policy.parse_dt(world["scenario_now"]), world["persona"]["email"])
    assert [row["thread_id"] for row in rows] == [row["thread_id"] for row in expected]
    assert [row["category"] for row in rows] == [row["category"] for row in expected]
    ranks = [row["attention_rank"] for row in rows]
    assert ranks == sorted(ranks) and rows[0]["attention_rank"] == min(ranks)


def test_detected_injections_are_quarantined_sorted_last_and_withheld(api: Api):
    rows = api.get("/api/inbox_triage/status")["rows"]
    quarantined = [row for row in rows if row["category"] == "quarantine"]
    suspicious = [row for row in rows if row["injection_patterns"] and row["trust"] == "unknown"]
    assert quarantined and quarantined == suspicious
    assert rows[-len(quarantined):] == quarantined
    for row in quarantined:
        assert row["snippet"] == "" and row["proposal"] is None
        shown = api.post("/api/systems_of_record/read", {
            "name": "mail_get_thread", "arguments": {"thread_id": row["thread_id"]}})["model_facing_result"]
        assert shown["subject"].startswith("[withheld") and shown["content"].startswith("[withheld")
        person = api.get(f"/api/inbox_triage/thread/{row['thread_id']}")
        assert person["body"] and person["warning"], "a person may still read it"


def test_the_tripwire_is_shown_as_the_weak_signal_it_is(api: Api):
    status = api.get("/api/inbox_triage/status")
    unknown = [row for row in status["rows"] if row["trust"] == "unknown"]
    assert status["unknown_senders"]["threads"] == len(unknown)
    assert status["unknown_senders"]["flagged_by_tripwire"] == sum(bool(row["injection_patterns"])
                                                                   for row in unknown)
    assert "31%" in status["tripwire"]["statement"]


def test_extraction_links_tasks_to_threads_and_never_raises_one_twice(api: Api):
    before = api.get("/api/inbox_triage/status")["rows"]
    wanted = [row for row in before if row["category"] in ("reply", "task", "delegate")]
    first = api.post("/api/inbox_triage/extract")
    assert len(first["created"]) == len(wanted) and first["suppressed_duplicates"] == []
    tasks = {item["task_id"]: item for item in api.get("/api/assistant/tasks")["open"]}
    for made in first["created"]:
        task = tasks[made["task_id"]]
        assert task["source_type"] == "mail" and task["source_ref"] == made["thread_id"]
    after = {row["thread_id"]: row for row in api.get("/api/inbox_triage/status")["rows"]}
    for task in tasks.values():
        row = after[task["source_ref"]]
        assert row["category"] == "tracked" and row["tracked_task_id"] == task["task_id"]
    again = api.post("/api/inbox_triage/extract")
    assert again["created"] == [] and again["drafts"] == []
    assert len(again["tracked"]) == len(wanted)
    assert len(api.get("/api/assistant/tasks")["open"]) == len(tasks)


def test_extraction_touches_no_quarantined_thread_and_sends_nothing(api: Api):
    result = api.post("/api/inbox_triage/extract")
    quarantined = set(result["quarantined"])
    assert quarantined
    assert not quarantined & {item["thread_id"] for item in result["created"] + result["drafts"]}
    drafts = api.read("mail_list_drafts")["drafts"]
    assert len(drafts) == len(result["drafts"]) and not quarantined & {item["thread_id"] for item in drafts}
    assert api.read("mail_list_sent")["sent"] == []
    assert api.get("/api/systems_of_record/effects")["effects"] == []


def test_a_quarantined_thread_is_never_answered(api: Api):
    held = next(row for row in api.get("/api/inbox_triage/status")["rows"] if row["category"] == "quarantine")
    asked = api.turn(f"Send a reply on thread `{held['thread_id']}`.")
    assert asked["status"] == "completed" and asked["pending_actions"] == []
    for tool in ("mail_send_message", "mail_create_draft"):
        api.post("/api/approvals/draft", {"name": tool, "arguments": {
            "to": [held["from_email"]], "subject": "Re", "body": "ok", "thread_id": held["thread_id"]}},
            expect=409 if tool == "mail_send_message" else 400)
    assert api.read("mail_list_sent")["sent"] == [] and api.read("mail_list_drafts")["drafts"] == []
    assert api.get("/api/approvals/status")["pending"] == []


# ── Calendar ─────────────────────────────────────────────────────────────────

def test_free_slots_avoid_every_event_and_stay_inside_working_hours(api: Api, rules: dict):
    day = api.get("/api/calendar_intel/status")["day"]
    opens, closes = (minutes(part) for part in rules["working_hours"].split(" to "))
    now = api.now()
    for slot in day["free_slots"]:
        assert opens <= minutes(slot["start_local"]) < minutes(slot["end_local"]) <= closes
        assert slot["minutes"] >= rules["minimum_slot_minutes"]
        assert datetime.fromisoformat(slot["start"]) >= now, "time that has passed is not free"
        assert _overlaps(slot["start"], slot["end"], day["events"]) == []
    persona = build_world()["persona"]
    expected = policy.free_slots(day["events"], now.date(), persona, not_before=now)
    assert [(s["start_local"], s["end_local"]) for s in day["free_slots"]] == \
        [(s["start_local"], s["end_local"]) for s in expected]


def test_meetings_before_the_earliest_time_are_flagged(api: Api, rules: dict):
    day = api.get("/api/calendar_intel/status")["day"]
    earliest = minutes(rules["no_meetings_before"])
    early = [item["event_id"] for item in day["events"]
             if item["kind"] == "meeting" and minutes(item["start"][11:16]) < earliest]
    assert [item["event_id"] for item in day["meeting_rule_violations"]] == early


def test_each_day_is_judged_on_its_own_load(api: Api, rules: dict):
    for load in api.get("/api/calendar_intel/status")["week"]:
        assert load["overbooked"] == (load["meeting_minutes"] > rules["max_meeting_minutes_per_day"])


def test_the_governed_reading_differs_from_the_naive_one(api: Api):
    free = api.post("/api/governed_meaning/compare", {"question": "free"})
    day = api.get("/api/calendar_intel/status")["day"]
    assert free["governed"]["answer"] == day["free_slots"] and free["governed"]["source"] == "policy.free_slots"
    assert sum(slot["minutes"] for slot in free["naive"]["answer"]) > day["load"]["free_minutes"]
    vip = api.post("/api/governed_meaning/compare", {"question": "vip"})
    flagged = {item["email"] for item in build_world()["contacts"] if item["is_vip"]}
    assert {item["id"] for item in vip["governed"]["answer"]} == flagged


# ── Approval gates ───────────────────────────────────────────────────────────

def test_a_send_pauses_at_the_approval_interrupt_and_resumes_the_same_run(api: Api):
    thread = _actionable(api)
    paused = api.turn(f"Send a reply on thread `{thread['thread_id']}`.", thread_id="send-approve")
    assert paused["status"] == "awaiting_approval" and paused["answer"] is None
    action = paused["pending_actions"][0]
    assert action["tool_name"] == "mail_send_message" and action["state"] == "DRAFTED"
    assert action["payload"]["to"] == [thread["from_email"]]
    assert paused["trace"]["nodes"][-1] == "draft_effects"
    assert api.read("mail_list_sent")["sent"] == [], "nothing leaves before the decision"
    assert api.post("/api/assistant/turn", {"message": "Hello", "thread_id": "send-approve"}, expect=409)

    done = api.post("/api/assistant/resume", {"thread_id": "send-approve",
                                              "decisions": {action["action_id"]: "approve"}})
    assert done["status"] == "completed" and done["run_id"] == paused["run_id"]
    assert "human_review" in done["trace"]["nodes"] and done["trace"]["nodes"][-1] == "persist"
    sent = api.read("mail_list_sent")["sent"]
    assert len(sent) == 1 and sent[0]["to"] == [thread["from_email"]]
    logged = next(item for item in api.get("/api/approvals/status")["log"]
                  if item["action_id"] == action["action_id"])
    assert logged["state"] == "EXECUTED" and logged["delivery"] and logged["decided_at"]


def test_a_rejected_approval_reaches_the_agent_as_a_declined_tool_result(api: Api):
    thread = _actionable(api)
    paused = api.turn(f"Send a reply on thread `{thread['thread_id']}`.", thread_id="send-reject")
    action = paused["pending_actions"][0]
    done = api.post("/api/assistant/resume", {"thread_id": "send-reject", "note": "Not now.",
                                              "decisions": {action["action_id"]: "reject"}})
    assert done["status"] == "completed" and done["run_id"] == paused["run_id"]
    assert api.read("mail_list_sent")["sent"] == []
    assert api.get("/api/systems_of_record/effects")["effects"] == []

    turn = api.get("/api/assistant/thread/send-reject")["last_turn"]
    result = next(item for item in turn if item["type"] == "tool" and item["name"] == "mail_send_message")
    assert result["status"] == "error" and result["content"]["status"] == "declined_by_user"
    assert "Do not retry" in result["content"]["detail"] and result["content"]["note"] == "Not now."
    after = turn[turn.index(result) + 1:]
    assert [item["type"] for item in after] == ["ai"] and after[0]["tool_calls"] == [], "it did not retry"
    assert "declined" in done["answer"].lower()
    logged = next(item for item in api.get("/api/approvals/status")["log"]
                  if item["action_id"] == action["action_id"])
    assert logged["state"] == "REJECTED" and logged["delivery"].startswith("not executed")


def test_a_stranger_off_the_thread_is_flagged_before_anything_is_drafted(api: Api):
    thread = _actionable(api)
    risk = api.post("/api/approvals/risk", {"to": ["someone@example.com"], "thread_id": thread["thread_id"]})
    assert risk["level"] == "high"
    assert set(risk["flagged"][0]["reasons"]) == {"not_on_thread", "unknown_contact", "external_domain"}
    drafted = api.post("/api/approvals/draft", {"name": "mail_send_message", "arguments": {
        "to": ["someone@example.com"], "subject": "x", "body": "y", "thread_id": thread["thread_id"]}})
    assert drafted["state"] == "DRAFTED" and drafted["risk"]["level"] == "high"
    rejected = api.post(f"/api/approvals/{drafted['action_id']}/decide", {"decision": "reject"})
    assert rejected["action"]["state"] == "REJECTED" and api.read("mail_list_sent")["sent"] == []
    api.post("/api/approvals/draft", {"name": "mail_trash_thread", "arguments": {"thread_id": "x"}}, expect=403)


def test_time_blocks_wait_for_approval_and_avoid_every_event(api: Api, rules: dict):
    api.post("/api/inbox_triage/extract")
    before = api.get("/api/calendar_intel/status")["day"]["events"]
    paused = api.turn("Time-block my top three tasks for today.", thread_id="blocks")
    assert paused["status"] == "awaiting_approval"
    blocks = paused["pending_actions"]
    assert blocks and all(item["tool_name"] == "calendar_create_event" for item in blocks)
    top = [item["task_id"] for item in api.get("/api/assistant/tasks")["open"][:3]]
    opens, closes = (minutes(part) for part in rules["working_hours"].split(" to "))
    for item in blocks:
        payload = item["payload"]
        assert _overlaps(payload["start"], payload["end"], before) == []
        assert opens <= minutes(payload["start"][11:16]) and minutes(payload["end"][11:16]) <= closes
        assert any(task in payload["description"] for task in top)
    assert api.get("/api/calendar_intel/status")["day"]["events"] == before, "the calendar is untouched"

    decisions = {item["action_id"]: "approve" for item in blocks}
    done = api.post("/api/assistant/resume", {"thread_id": "blocks", "decisions": decisions})
    assert done["status"] == "completed"
    after = api.get("/api/calendar_intel/status")["day"]["events"]
    assert len(after) == len(before) + len(blocks)
    assert "/plans/today.md" in api.get("/api/memory_layer/plan")["path"]
    assert api.get("/api/memory_layer/plan")["content"].count("\n- ") + 1 >= len(blocks)


def test_an_automatic_action_can_be_undone_and_a_sent_mail_cannot(api: Api):
    api.turn("Add a task: read the quarterly filing")
    added = next(item for item in api.get("/api/approvals/status")["log"] if item["tool_name"] == "task_add")
    assert added["tier"] == "automatic" and added["state"] == "EXECUTED" and added["undoable"]
    assert added["reason"] and "Undo" in added["undo_hint"]
    undone = api.post(f"/api/approvals/{added['action_id']}/undo")
    assert not undone["undoable"] and api.get("/api/assistant/tasks")["open"] == []
    api.post(f"/api/approvals/{added['action_id']}/undo", expect=409)


# ── Focus sessions and the scheduler ─────────────────────────────────────────

def test_a_pomodoro_job_fires_and_produces_a_notification(api: Api):
    api.post("/api/inbox_triage/extract")
    task = api.get("/api/assistant/tasks")["open"][0]
    started = api.post("/api/focus_sessions/start", {"task_id": task["task_id"], "demo_seconds": 3})
    session, job = started["session"], started["job"]
    assert started["status"] == "started" and session["status"] == "RUNNING" and session["compressed"]
    assert job["kind"] == "pomodoro" and job["state"] == "ARMED" and job["clock"] == "real"
    assert job["task_id"] == task["task_id"] and 0 < job["seconds_remaining"] <= 3
    api.post("/api/focus_sessions/distraction", {"text": "Look up the filing deadline"})
    assert api.post("/api/focus_sessions/start", {"demo_seconds": 3})["status"] == "already_running"

    note = api.wait_for(lambda: next((item for item in api.get("/api/notifications")["notifications"]
                                      if item["job_id"] == job["job_id"]), None), 15, "the timer to fire")
    assert note["kind"] == "pomodoro" and note["title"] == "Session finished"
    assert "Look up the filing deadline" in note["body"] and task["title"] in note["body"]
    fired = next(item for item in api.get("/api/routines/jobs")["jobs"] if item["job_id"] == job["job_id"])
    assert fired["state"] == "DELIVERED" and fired["notification"]["notification_id"] == note["notification_id"]
    logged = api.get("/api/focus_sessions/status")
    assert logged["running"] is None and logged["log"][0]["status"] == "COMPLETED"
    assert logged["log"][0]["actual_minutes"] == logged["log"][0]["planned_minutes"]
    run = api.get(f"/api/the_loop/trace/{fired['run_id']}")
    assert run["trigger"] == "pomodoro" and run["responder"] == "scripted responder"


def test_the_model_facing_timer_is_clamped_and_stopping_cancels_the_job(api: Api):
    asked = api.turn("Start a 300-minute focus session on the annual report.")
    assert asked["status"] == "completed"
    running = api.get("/api/focus_sessions/status")["running"]
    assert running["planned_minutes"] == 90 and not running["compressed"]
    assert running["task_title"], "a task was created for the request"
    stopped = api.post("/api/focus_sessions/stop", {"reason": "test"})
    assert stopped["session"]["status"] == "INTERRUPTED"
    job = next(item for item in api.get("/api/routines/jobs")["jobs"] if item["job_id"] == running["job_id"])
    assert job["state"] == "CANCELLED"


def test_a_scheduled_routine_fires_when_the_clock_reaches_it(api: Api):
    wrap = next(item for item in api.get("/api/routines/status")["jobs"]
                if item["kind"] == "end_of_day_wrap" and item["state"] == "ARMED")
    assert wrap["clock"] == "harness" and wrap["seconds_remaining"] > 0
    api.post("/api/memory_layer/capture", {"text": "Ask about the conveyance fee"})
    api.post("/api/clock", {"now": wrap["fires_at"]})
    done = api.wait_for(lambda: next((item for item in api.get("/api/routines/jobs")["jobs"]
                                      if item["job_id"] == wrap["job_id"] and item["state"] == "DELIVERED"),
                                     None), 15, "the end-of-day wrap to fire")
    assert done["notification"]["kind"] == "end_of_day_wrap"
    run = api.get(f"/api/the_loop/trace/{done['run_id']}")
    assert run["trigger"] == "end_of_day_wrap" and "end_workday" in [call["name"] for call in
                                                                      run["trace"]["tool_calls"]]
    scratch = api.get("/api/memory_layer/status")
    assert scratch["scratch"]["queue"][0]["outcome"] == "PROMOTED"
    assert [item["title"] for item in api.get("/api/assistant/tasks")["open"]] == ["Ask about the conveyance fee"]
    assert scratch["memories"]["episode"], "the day was written as an episode"
    rearmed = next(item for item in api.get("/api/routines/jobs")["jobs"]
                   if item["kind"] == "end_of_day_wrap" and item["state"] == "ARMED")
    assert rearmed["fires_at"] > wrap["fires_at"]


def test_a_meeting_that_is_about_to_start_triggers_its_prep(api: Api):
    day = api.get("/api/calendar_intel/status")["day"]
    meeting = next(item for item in day["events"] if item["kind"] == "meeting"
                   and datetime.fromisoformat(item["start"]) > api.now())
    preset = next(item for item in api.get("/api/clock")["presets"] if "next meeting" in item["label"])
    api.post("/api/clock", {"now": preset["now"]})
    done = api.wait_for(lambda: next((item for item in api.get("/api/routines/jobs")["jobs"]
                                      if item["kind"] == "meeting_prep" and item["state"] == "DELIVERED"),
                                     None), 15, "meeting prep to fire")
    assert done["payload"]["event_id"] == meeting["event_id"]
    assert meeting["title"] in done["notification"]["body"]
    api.post("/api/routines/triggers/evaluate")
    prepared = [item for item in api.get("/api/routines/jobs")["jobs"] if item["kind"] == "meeting_prep"]
    assert len(prepared) == 1, "one meeting is prepared once"


# ── Memory ───────────────────────────────────────────────────────────────────

def test_a_stated_preference_is_recalled_in_a_new_session(api: Api):
    said = api.turn("From now on keep Friday afternoons free of meetings.", thread_id="monday")
    assert said["status"] == "completed"
    stored = api.get("/api/memory_layer/status")["memories"]["preference"]
    assert [item["content"] for item in stored] == ["Keep Friday afternoons free of meetings."]

    later = api.turn("What should I know before I plan Friday?", thread_id="another-day",
                     session_id="workday-another-day")
    assert "Keep Friday afternoons free of meetings." in later["answer"]
    fresh = api.get("/api/assistant/thread/another-day")
    assert [item["role"] for item in fresh["messages"]] == ["user", "assistant"], "no shared conversation"
    context = api.post("/api/the_loop/context", {"query": "Plan my week"})
    assert "Keep Friday afternoons free of meetings." in context["first_user_message"]
    assert "Keep Friday afternoons" not in context["stable_prefix"]["system_prompt"]


def test_promotion_happens_once_per_content_hash(api: Api):
    api.post("/api/memory_layer/capture", {"text": "Renew the bar membership"})
    first = api.post("/api/memory_layer/session/end")
    assert first["promoted"] == 1 and first["outcomes"][0]["target"] == "task"
    api.post("/api/memory_layer/session/start")
    api.post("/api/memory_layer/capture", {"text": "Renew the bar   membership"})
    second = api.post("/api/memory_layer/session/end")
    assert second["promoted"] == 0 and second["duplicates"] == 1
    assert second["outcomes"][0]["reference"] == first["outcomes"][0]["reference"]
    assert len(api.get("/api/assistant/tasks")["open"]) == 1


def test_forgetting_follows_the_clock(api: Api):
    api.turn("Add a task: look into a document management system")
    task = api.get("/api/assistant/tasks")["open"][0]
    api.post("/api/memory_layer/write", {"memory_type": "fact", "content": "The filing is due in ten days.",
                                         "ttl_days": 10})
    api.post(f"/api/assistant/tasks/{task['task_id']}/complete")
    assert api.get("/api/memory_layer/decay")["faded_done"] == []
    api.post(f"/api/assistant/tasks/{task['task_id']}/reopen")

    later = next(item for item in api.get("/api/clock")["presets"] if "31 days" in item["label"])
    api.post("/api/clock", {"now": later["now"]})
    decay = api.post("/api/memory_layer/decay/sweep")
    assert [item["task_id"] for item in decay["drop_candidates"]] == [task["task_id"]]
    assert [item["content"] for item in decay["expired"]] == ["The filing is due in ten days."]
    assert api.post("/api/memory_layer/recall", {"query": "filing due"})["recalled"] == []


# ── Skills and the loop ──────────────────────────────────────────────────────

def test_skills_disclose_one_body_on_demand(api: Api):
    status = api.get("/api/skills/status")
    assert [item["name"] for item in status["manifests"]] == [
        "morning-brief", "inbox-triage", "meeting-prep", "time-block-tasks", "focus-session",
        "end-of-day-wrap", "weekly-review"]
    assert all(set(item) == {"name", "description"} for item in status["manifests"])
    match = api.post("/api/skills/match", {"query": "Review my week"})
    assert match["disclosed_skill"]["name"] == "weekly-review" and match["disclosed_skill"]["body"]
    tokens = match["token_comparison"]
    assert tokens["manifests_only"] < tokens["progressive"] < tokens["dump_everything"]


def test_the_morning_brief_follows_the_governed_order(api: Api):
    rows = api.get("/api/inbox_triage/status")["rows"]
    day = api.get("/api/calendar_intel/status")["day"]
    brief = api.turn("Prepare my morning brief.")
    answer, trace = brief["answer"], brief["trace"]
    first = next(row for row in rows if row["category"] in ("reply", "task", "delegate"))
    assert answer.index(first["thread_id"]) == min(answer.index(row["thread_id"]) for row in rows
                                                   if row["thread_id"] in answer)
    for event in day["events"]:
        assert event["event_id"] in answer
    if day["meeting_rule_violations"]:
        assert f"no-meetings-before-{day['rules']['no_meetings_before']}" in answer
    assert all(row["thread_id"] in answer for row in rows if row["category"] == "quarantine")
    called = [call["name"] for call in trace["tool_calls"]]
    assert called[0] == "load_skill" and {"triage_inbox", "day_overview", "task_list"} <= set(called)
    reads = {item["tool"] for call in trace["tool_calls"] for item in call["mcp"]}
    assert {"mail_search_threads", "calendar_list_events"} <= reads, "read through MCP"
    assert trace["nodes"] == ["assemble_context", "call_model", "call_model", "persist"]
    assert trace["responder"] == "scripted responder" and trace["tokens"]["total"] == 0


def test_the_weekly_review_fills_from_what_was_recorded(api: Api):
    api.post("/api/inbox_triage/extract")
    report = api.post("/api/routines/simulate_week", {"days": 2})
    assert [item["focus_sessions"] > 0 for item in report["days"]] == [True, True]
    review = api.get("/api/weekly_review/status")["review"]
    log = api.get("/api/focus_sessions/status")["log"]
    assert not review["empty"] and log and all(item["note"].startswith("simulated week") for item in log)
    summary = policy.focus_summary(log)
    assert {item["task_id"]: item["minutes"] for item in review["time_by_task"]} == summary["minutes_by_task"]
    assert review["focus"]["actual_minutes"] == summary["actual_minutes"]
    done = sum(item["completed"] for item in report["days"])
    assert review["planned_vs_done"]["done"] == done
    asked = api.post("/api/weekly_review/run")
    assert asked["trigger"] == "weekly_review" and "Where time went" in asked["answer"]


def test_a_moment_without_an_offset_is_read_in_the_owner_timezone(api: Api):
    api.turn("Add a task: file the quarterly return")
    task = api.get("/api/assistant/tasks")["open"][0]
    day = api.now().date().isoformat()
    changed = api.client.patch(f"/api/assistant/tasks/{task['task_id']}", json={"due_at": f"{day}T16:00"}).json()
    assert changed["due_at"][:16] == f"{day}T16:00" and changed["due_at"][16:] == api.now().isoformat()[19:]
    assert changed["urgent"], "due within 24 hours"
    api.post("/api/clock", {"now": "not a moment"}, expect=400)
    moved = api.post("/api/clock", {"now": f"{day}T12:00"})
    assert moved["now"][:16] == f"{day}T12:00" and moved["mode"] == "practice"


def test_claude_takes_over_a_conversation_that_began_on_the_scripted_responder(api: Api, monkeypatch):
    """A key added after a conversation began must not leave that conversation on the fallback."""
    from langchain_core.messages import AIMessage

    from backend.core import llm_client

    first = api.turn("Prepare my morning brief.")
    assert first["responder"] == "scripted responder"

    asked = []

    async def answer(kind, system_prompt, messages):
        asked.append((kind, len(messages)))
        return AIMessage(content="Claude answered."), {"responder": llm_client.claude_label()}

    monkeypatch.setattr(llm_client, "default_responder", lambda: "claude")
    monkeypatch.setattr(llm_client, "respond", answer)
    second = api.turn("And what comes after that?", thread_id=first["thread_id"])

    assert second["responder"] == llm_client.claude_label()
    assert second["answer"] == "Claude answered."
    kind, history = asked[0]
    assert kind == "claude" and history > 2, "Claude is given the conversation so far"
    assert api.get(f"/api/assistant/thread/{first['thread_id']}")["responder"] == llm_client.claude_label()


def test_a_timer_is_not_left_armed_when_its_session_cannot_be_stored(api: Api, monkeypatch):
    from backend.core import focus, store

    real = store.execute

    def refuse(sql, *args, **kwargs):
        if "INSERT INTO ppa_focus_sessions" in sql:
            raise RuntimeError("the row could not be written")
        return real(sql, *args, **kwargs)

    monkeypatch.setattr(store, "execute", refuse)
    with pytest.raises(RuntimeError):
        focus.start(minutes=25)
    monkeypatch.undo()
    jobs = api.get("/api/routines/jobs")["jobs"]
    assert [job["state"] for job in jobs if job["kind"] == "pomodoro"] == ["CANCELLED"]
    assert api.get("/api/focus_sessions/status")["running"] is None


def test_the_pages_are_checked_against_the_files_on_every_load(started: Api):
    for path in ("/", "/app.js", "/system-one.js", "/styles.css"):
        response = started.client.get(path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-cache", path
