"""The practice world as one dictionary, for code that does not speak MCP.

The custom harness reads mail, calendar and notes through the MCP gateway.
Some consumers cannot: a coding harness that only reads files, or a test that
must run offline. ``build_world`` gives them the same practice workspace as a
plain snapshot at one moment in time.

Harness-owned state starts empty by design. Tasks, focus sessions, pages and
memories are created by using the assistant, never seeded.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from practice import PracticeWorkspace
from settings import owner_settings
from textutil import display_name


def build_world(now: str | None = None, days_ahead: int = 14) -> dict[str, Any]:
    """Snapshot the practice workspace at ``now`` (default: the scenario clock)."""
    workspace = PracticeWorkspace(now=now)
    today = workspace.now.date()
    events = workspace.list_events(today.isoformat(),
                                   (today + timedelta(days=days_ahead)).isoformat())["events"]
    persona = {"user_id": workspace.owner_email.split("@")[0].replace(".", "-"),
               "name": display_name(workspace.owner_email), "email": workspace.owner_email,
               "timezone": workspace.timezone, **owner_settings()}
    return {
        "anchor_day": today.isoformat(),
        "scenario_now": workspace.now.isoformat(timespec="minutes"),
        "persona": persona,
        "contacts": workspace.contacts(),
        "emails": workspace.inbox(),
        "events": events,
        "pages": [], "tasks": [], "focus_log": [], "seed_memories": [],
        "benign_probe": workspace.benign_probe,
        "provenance": workspace.meta,
    }
