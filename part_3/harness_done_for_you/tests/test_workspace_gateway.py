"""Offline tests for the MCP gateway of the done-for-you track.

No key, no network and no model: the three servers are called in process.
The data is real, so each test states a rule that must hold, not a
hand-picked answer.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK))

import workspace_gateway as gateway  # noqa: E402
from gateway import Workspace  # noqa: E402  (the shared workspace, put on the path by the import above)

TUESDAY = "2001-08-07"


@pytest.fixture()
def servers(tmp_path, monkeypatch):
    monkeypatch.setenv("PPA_HOME", str(tmp_path / "ppa_home"))
    monkeypatch.setenv("PPA_PRACTICE_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("PPA_PRACTICE_NOW", TUESDAY + "T08:30")
    monkeypatch.setenv("PPA_GENERATED_CALENDAR", "1")
    return gateway.build_servers(Workspace())


def call(server, tool: str, **arguments) -> dict:
    result = asyncio.run(server.call_tool(tool, arguments))
    content = result.content if hasattr(result, "content") else result[0]
    return json.loads(content[0].text)


def test_every_published_tool_is_registered(servers):
    for name, server in servers.items():
        listed = {tool.name for tool in asyncio.run(server.list_tools())}
        assert listed == set(gateway.TOOLS[name])


def test_every_tool_has_the_description_from_the_table(servers):
    for name, server in servers.items():
        for tool in asyncio.run(server.list_tools()):
            assert tool.description == gateway.TOOLS[name][tool.name]


def test_inbox_is_read_at_the_pinned_clock(servers):
    threads = call(servers["mail"], "mail_search_threads", max_results=50)["threads"]
    assert threads, "the practice inbox is not empty on the scenario morning"
    assert all(thread["received_at"] <= TUESDAY + "T08:30-05:00" for thread in threads)


def test_a_draft_is_saved_and_nothing_is_sent(servers):
    saved = call(servers["mail"], "mail_create_draft", to=["someone@example.com"], subject="Hello", body="Draft.")
    assert saved["sent"] is False
    assert len(call(servers["mail"], "mail_list_drafts")["drafts"]) == 1
    assert call(servers["mail"], "mail_list_sent")["sent"] == []


def test_a_send_in_the_practice_workspace_is_simulated_and_recorded(servers):
    outcome = call(servers["mail"], "mail_send_message", to=["someone@example.com"], subject="Hello", body="Body.")
    assert "simulated" in outcome["delivery"]
    assert [message["subject"] for message in call(servers["mail"], "mail_list_sent")["sent"]] == ["Hello"]


def test_a_created_event_appears_on_the_calendar(servers):
    before = call(servers["calendar"], "calendar_list_events", start_date=TUESDAY)["events"]
    call(servers["calendar"], "calendar_create_event", title="Focus", start=TUESDAY + "T15:30-05:00",
         end=TUESDAY + "T16:00-05:00")
    after = call(servers["calendar"], "calendar_list_events", start_date=TUESDAY)["events"]
    assert len(after) == len(before) + 1
    assert any(event["title"] == "Focus" for event in after)


def test_state_survives_a_restart(servers, tmp_path):
    call(servers["notes"], "notes_create_page", title="Kept", body="Still here.")
    again = gateway.build_servers(Workspace())          # a new gateway process reads the same state file
    assert any(page["title"] == "Kept" for page in call(again["notes"], "notes_search", query="Kept")["pages"])


def test_a_provider_failure_is_a_result_not_an_exception(servers):
    outcome = call(servers["notes"], "notes_get_page", page_id="no-such-page")
    assert "error" in outcome or outcome.get("page") is None
