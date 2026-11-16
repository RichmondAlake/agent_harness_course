"""Owner settings and the local connection store.

Settings are how the assistant should behave for one person: timezone,
working hours, the earliest acceptable meeting, Pomodoro length. They are
configuration, not data, and every one of them can be changed by the owner.

Connection secrets (an app password, an integration token) live in one local
file that only the owner can read. They are never written to the repository,
never returned by an API, and never shown in a log.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "work_start": "09:00",
    "work_end": "17:30",
    "no_meetings_before": "10:00",
    "pomodoro_minutes": 25,
    "break_minutes": 5,
    "max_meeting_minutes_per_day": 240,
    "inbox_days": 5,
}

SECRET_FIELDS = {"password", "token", "secret", "api_key", "ics_url"}


def owner_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Defaults, then ``PPA_*`` environment variables, then explicit overrides."""
    values = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        raw = os.environ.get(f"PPA_{key.upper()}")
        if raw:
            values[key] = int(raw) if isinstance(default, int) else raw
    values.update(overrides or {})
    return values


def store_path() -> Path:
    root = Path(os.environ.get("PPA_HOME", Path.home() / ".ppa"))
    return root / "connections.json"


def load_connections() -> dict[str, Any]:
    path = store_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_connections(connections: dict[str, Any]) -> Path:
    """Write the store so that only the current user can read it."""
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(stat.S_IRWXU)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(connections, handle, indent=2, sort_keys=True)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def redact(settings: dict[str, Any]) -> dict[str, Any]:
    """A copy that is safe to return from an API or print in a notebook."""
    return {key: ("set" if key in SECRET_FIELDS and value else value)
            for key, value in settings.items() if key not in SECRET_FIELDS or value}
