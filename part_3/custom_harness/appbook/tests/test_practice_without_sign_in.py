"""Nothing here needs an account, and the practice calendar says where each event came from."""
from __future__ import annotations

from datetime import datetime, timedelta

from conftest import Api

CHAPTERS = ["/api/assistant/status", "/api/architecture", "/api/connections/status",
            "/api/systems_of_record/status", "/api/memory_layer/status", "/api/governed_meaning/status",
            "/api/inbox_triage/status", "/api/calendar_intel/status", "/api/focus_sessions/status",
            "/api/skills/status", "/api/approvals/status", "/api/the_loop/status", "/api/routines/status",
            "/api/weekly_review/status", "/api/data_explorer/tables"]
PREFIX = "Working session: "


def _events(api: Api, days: int = 5) -> list[dict]:
    first = api.now().date()
    found = {}
    for offset in range(days):
        day = api.get(f"/api/calendar_intel/status?date={(first + timedelta(days=offset)).isoformat()}")["day"]
        found.update({item["event_id"]: item for item in day["events"]})
    return list(found.values())


def test_every_chapter_answers_with_nothing_connected(api: Api):
    connections = api.get("/api/connections/status")
    assert connections["practice"] and {item["provider"] for item in connections["systems"].values()} == {"practice"}
    assert "Nothing here needs an account" in connections["no_sign_in"]["title"]
    assert "optional" in connections["no_sign_in"]["optional"]
    for path in CHAPTERS:
        answer = api.get(path)
        assert answer and "error" not in answer, path
    assert api.turn("Prepare my morning brief.")["status"] == "completed"


def test_the_disclosure_says_what_leaves_the_machine(api: Api):
    connections = api.get("/api/connections/status")
    leaving = next(item for item in connections["disclosure"] if item["title"] == "What leaves this machine")
    assert "no text is sent to any model" in leaving["text"], "the scripted responder is in charge here"
    assert "Tracing to LangSmith is off" in leaving["text"] and not connections["tracing"]["active"]
    assert "Web search is not configured" in leaving["text"]
    assert not api.get("/api/status")["tracing"]["active"]


def test_every_practice_event_names_its_layer(api: Api):
    owner = api.persona()["email"]
    events = _events(api)
    assert events and {item["source"] for item in events} <= {"invitation", "generated"}
    generated = [item for item in events if item["source"] == "generated"]
    invited = [item for item in events if item["source"] == "invitation"]
    assert generated, "the appbook turns the generated layer on unless PPA_GENERATED_CALENDAR=0"
    for item in generated:
        assert item["title"].startswith(PREFIX) and item["attendees"] == [owner] and item["related_thread"]
        assert not any(datetime.fromisoformat(item["start"]) < datetime.fromisoformat(other["end"])
                       and datetime.fromisoformat(other["start"]) < datetime.fromisoformat(item["end"])
                       for other in invited), "an invitation always wins"
    today = api.get("/api/calendar_intel/status")
    counted = {layer["source"]: layer["events"] for layer in today["layers"]}
    assert counted == {source: sum(item["source"] == source for item in today["day"]["events"])
                       for source in {item["source"] for item in today["day"]["events"]}}
    assert all(layer["about"].endswith(".") for layer in today["layers"])


def test_preparing_a_generated_session_searches_for_its_matter(api: Api):
    session = next(item for item in _events(api) if item["source"] == "generated")
    prepared = api.get(f"/api/calendar_intel/prep/{session['event_id']}")
    assert prepared["topic"] == session["title"][len(PREFIX):] and not prepared["topic"].startswith(PREFIX)
    assert prepared["related_thread"]["thread_id"] == session["related_thread"]
    assert session["related_thread"] in [item["thread_id"] for item in prepared["earlier_threads"]], \
        "the session's own thread is the evidence and stays in"
    assert prepared["people"] == [], "the owner is the only attendee"

    answer = api.turn(f"Prepare me for the meeting with event ID `{session['event_id']}`.")
    assert answer["status"] == "completed"
    assert "The thread this session is about" in answer["answer"]
    assert session["related_thread"] in answer["answer"] and "The invitation" not in answer["answer"]


def test_preparing_an_invitation_keeps_the_invitation(api: Api):
    invited = next((item for item in _events(api) if item["source"] == "invitation"), None)
    assert invited is not None
    prepared = api.get(f"/api/calendar_intel/prep/{invited['event_id']}")
    assert prepared["topic"] == invited["title"]
    if invited.get("related_thread"):
        assert prepared["related_thread"]["thread_id"] == invited["related_thread"]
