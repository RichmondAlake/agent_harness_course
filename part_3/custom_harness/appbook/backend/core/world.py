"""The harness's view of the person it works for.

Persona, contacts and the pinned clock arrive from the workspace gateway's
``/admin/world``. Nothing in the appbook names a person, an address or a
record; every such value is read from here or from an MCP result.
"""
from __future__ import annotations

import hashlib
from typing import Any

_state: dict[str, Any] = {"persona": None, "contacts": [], "scenario_now": None, "loaded": False}

PERSONA_KEYS = ("name", "email", "timezone", "work_start", "work_end", "no_meetings_before",
                "pomodoro_minutes", "break_minutes", "max_meeting_minutes_per_day")


def load(payload: dict[str, Any]) -> None:
    """Adopt the gateway's persona, contacts and pinned clock."""
    missing = [key for key in PERSONA_KEYS if key not in payload.get("persona", {})]
    if missing:
        raise ValueError(f"The gateway persona is missing: {', '.join(missing)}")
    _state.update(persona=dict(payload["persona"]), contacts=[dict(item) for item in payload.get("contacts", [])],
                  scenario_now=payload.get("scenario_now"), loaded=True)


def persona() -> dict[str, Any]:
    if not _state["loaded"]:
        raise RuntimeError("The workspace gateway has not supplied a persona yet")
    return _state["persona"]


def contacts() -> list[dict[str, Any]]:
    return _state["contacts"]


def scenario_now() -> str | None:
    """The pinned practice clock, or ``None`` when the real clock applies."""
    return _state["scenario_now"]


def set_scenario_now(value: str) -> None:
    _state["scenario_now"] = value


def owner_email() -> str:
    return persona()["email"].lower()


def owner_first_name() -> str:
    return persona()["name"].split()[0]


def own_domain() -> str:
    return owner_email().split("@", 1)[-1]


def user_id() -> str:
    return persona().get("user_id") or owner_email()


def identity() -> str:
    """A stable, file-safe key for the owner. Harness state is kept per owner."""
    return hashlib.sha256(owner_email().encode()).hexdigest()[:12]
