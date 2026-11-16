"""Tests that need their own application lifetimes: a restart, and a real connection.

The `folder` notes provider needs no credentials, so connecting it is enough to
move the whole workspace into real mode with the real clock and safe mode on.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import Api
from fastapi.testclient import TestClient

from backend.main import app

HOME = Path(os.environ["PPA_HOME"])


def _start(client: TestClient) -> Api:
    api = Api(client)
    api.wait_for(lambda: api.get("/api/status").get("ready"), 60, "the harness to start")
    return api


def test_timers_are_rearmed_from_the_database_after_a_restart():
    with TestClient(app) as client:
        api = _start(client)
        api.post("/api/reset", {"confirm": "reset"})
        started = api.post("/api/focus_sessions/start", {"minutes": 25, "demo_seconds": 8})
        job_id, session_id = started["job"]["job_id"], started["session"]["session_id"]
        assert api.get("/api/routines/status")["scheduler"]["rearmed_at_start"] == []

    # The application is down here: no scheduler thread, no gateway, no event loop.

    with TestClient(app) as client:
        api = _start(client)
        status = api.get("/api/routines/status")
        assert job_id in status["scheduler"]["rearmed_at_start"]
        job = next(item for item in status["jobs"] if item["job_id"] == job_id)
        assert job["rearmed_at"] and job["state"] in {"ARMED", "FIRED", "DELIVERED"}
        note = api.wait_for(lambda: next((item for item in api.get("/api/notifications")["notifications"]
                                          if item["job_id"] == job_id), None), 20, "the re-armed timer to fire")
        assert note["title"] == "Session finished"
        session = next(item for item in api.get("/api/focus_sessions/status")["log"]
                       if item["session_id"] == session_id)
        assert session["status"] == "COMPLETED" and session["actual_minutes"] == 25


def test_a_paused_run_survives_a_restart_and_resumes_from_its_checkpoint():
    with TestClient(app) as client:
        api = _start(client)
        api.post("/api/reset", {"confirm": "reset"})
        thread = next(row for row in api.get("/api/inbox_triage/status")["rows"]
                      if row["category"] in ("reply", "task"))
        paused = api.turn(f"Send a reply on thread `{thread['thread_id']}`.", thread_id="durable")
        action = paused["pending_actions"][0]["action_id"]

    with TestClient(app) as client:
        api = _start(client)
        waiting = api.get("/api/assistant/thread/durable")
        assert waiting["waiting_for_approval"]
        assert [item["action_id"] for item in waiting["pending_actions"]] == [action]
        done = api.post(f"/api/approvals/{action}/decide", {"decision": "approve"})
        assert done["action"]["state"] == "EXECUTED"
        assert done["run"]["status"] == "completed" and done["run"]["run_id"] == paused["run_id"]


def test_a_failed_connection_stores_nothing_and_echoes_no_secret():
    with TestClient(app) as client:
        api = _start(client)
        secret = "app-password-that-must-not-come-back"
        refused = client.post("/api/connections/connect", json={
            "system": "mail", "provider": "imap", "settings": {
                "address": "owner@appbook-tests.example", "password": secret,
                "imap_host": "127.0.0.1", "smtp_host": "127.0.0.1", "smtp_port": 465}})
        assert refused.status_code == 400 and secret not in refused.text
        status = api.get("/api/connections/status")
        assert status["practice"] and secret not in json.dumps(status)
        stored = HOME / "connections.json"
        assert not stored.exists() or "mail" not in json.loads(stored.read_text())
        fields = [field for provider in status["providers"]["mail"] for field in provider["fields"]]
        assert any(field["type"] == "password" for field in fields)
        assert len(status["disclosure"]) >= 4


def test_safe_mode_holds_an_approved_send_once_a_real_system_is_connected(tmp_path):
    with TestClient(app) as client:
        api = _start(client)
        try:
            joined = api.post("/api/connections/connect", {
                "system": "notes", "provider": "folder", "settings": {"path": str(tmp_path / "notes")}})
            assert joined["mode"] == "real" and not joined["practice"] and joined["safe_mode"]
            status = api.get("/api/status")
            assert status["clock"]["mode"] == "real" and status["clock"]["ticking"]
            assert status["owner"]["email"] == os.environ["PPA_OWNER_EMAIL"]
            api.post("/api/reset", {"confirm": "reset"})

            drafted = api.post("/api/approvals/draft", {"name": "mail_send_message", "arguments": {
                "to": ["someone@elsewhere.example"], "subject": "Hello", "body": "A real message."}})
            assert "held as a draft" in drafted["risk"]["safe_mode_effect"]
            decided = api.post(f"/api/approvals/{drafted['action_id']}/decide", {"decision": "approve"})
            action = decided["action"]
            assert action["state"] == "EXECUTED", "approved"
            assert action["delivery"].startswith("held by safe mode"), "but not delivered"
            effect = api.get("/api/systems_of_record/effects")["effects"][-1]
            assert effect["kind"] == "mail_send_message" and effect["outcome"]["delivered"] is False

            page = api.turn("Note: the folder provider keeps pages on this machine")
            assert page["status"] == "completed"
        finally:
            left = api.post("/api/connections/disconnect", {"system": "notes"})
        assert left["practice"] and api.get("/api/status")["clock"]["mode"] == "practice"


def test_the_practice_clock_is_where_it_was_left_after_a_restart():
    with TestClient(app) as client:
        api = _start(client)
        api.post("/api/reset", {"confirm": "reset"})
        start = api.get("/api/clock")["now"]
        preset = next(item for item in api.get("/api/clock")["presets"] if "31 days" in item["label"])
        moved = api.post("/api/clock", {"now": preset["now"]})["now"]
        assert moved != start

    with TestClient(app) as client:
        api = _start(client)
        assert api.get("/api/clock")["now"] == moved
        assert moved[:16] in api.get("/api/status")["workspace"]["systems"]["mail"]["detail"]
        assert api.post("/api/clock/reset")["now"] == start


def test_what_was_approved_is_still_in_the_workspace_after_a_restart():
    with TestClient(app) as client:
        api = _start(client)
        api.post("/api/reset", {"confirm": "reset"})
        day = api.get("/api/clock")["now"][:10]
        drafted = api.post("/api/approvals/draft", {
            "name": "calendar_create_event",
            "arguments": {"title": "Kept across a restart", "start": f"{day}T15:00", "end": f"{day}T16:00"}})
        api.post(f"/api/approvals/{drafted['action_id']}/decide", {"decision": "approve"})
        before = [item["title"] for item in api.get("/api/calendar_intel/status")["day"]["events"]]
        assert "Kept across a restart" in before
        assert [item["kind"] for item in api.get("/api/systems_of_record/effects")["effects"]] == [
            "calendar_create_event"]

    # The application and its gateway are down here.

    with TestClient(app) as client:
        api = _start(client)
        after = [item["title"] for item in api.get("/api/calendar_intel/status")["day"]["events"]]
        assert "Kept across a restart" in after, "an approved event must survive a restart"
        assert [item["kind"] for item in api.get("/api/systems_of_record/effects")["effects"]] == [
            "calendar_create_event"]
        api.post("/api/reset", {"confirm": "reset"})
        assert api.get("/api/systems_of_record/effects")["effects"] == []
        cleared = [item["title"] for item in api.get("/api/calendar_intel/status")["day"]["events"]]
        assert "Kept across a restart" not in cleared, "a reset empties what was kept"
