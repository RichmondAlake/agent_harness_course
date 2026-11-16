"""The harness clock.

The practice workspace pins the clock, and the gateway replays the mailbox
against it: moving the clock forward makes mail arrive and meetings get
announced. With a real mailbox or calendar connected nothing is pinned and the
real clock in the owner's timezone applies. Focus timers never use this clock:
a real job has to fire at a real time.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.core import store, world

PIN_KEY = "clock_pin"


def tz() -> ZoneInfo:
    return ZoneInfo(world.persona()["timezone"])


def mode() -> str:
    """``practice`` (pinned by the gateway), ``pinned`` (by the operator) or ``real``."""
    if world.scenario_now():
        return "practice"
    return "pinned" if store.get_meta(PIN_KEY) else "real"


def now() -> datetime:
    pinned = world.scenario_now() or store.get_meta(PIN_KEY)
    if pinned:
        return datetime.fromisoformat(pinned).astimezone(tz())
    return datetime.now(tz()).replace(microsecond=0)


def today() -> date:
    return now().date()


def stamp() -> str:
    return now().isoformat(timespec="seconds")


def at(day: date, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz())


def localise(value: str) -> datetime:
    """Read an ISO moment; a moment without an offset is in the owner's timezone."""
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=tz()) if moment.tzinfo is None else moment.astimezone(tz())


def parse_day(value: str | None) -> date:
    """Accept an ISO date, an ISO datetime, or nothing (today)."""
    return date.fromisoformat(value[:10]) if value else today()


def business_day(start: date, offset: int) -> date:
    day, step, remaining = start, (1 if offset >= 0 else -1), abs(offset)
    while remaining:
        day += timedelta(days=step)
        if day.weekday() < 5:
            remaining -= 1
    return day


def session_id(day: date | None = None) -> str:
    """A workday is one session."""
    return f"workday-{(day or today()).isoformat()}"


def pin(value: str | None) -> None:
    """Pin the harness clock when no practice clock exists. ``None`` returns to the real clock."""
    store.set_meta(PIN_KEY, localise(value).isoformat(timespec="minutes") if value else None)


def status() -> dict[str, Any]:
    current = now()
    return {"mode": mode(), "now": current.isoformat(timespec="seconds"),
            "weekday": current.strftime("%A"), "timezone": world.persona()["timezone"],
            "session_id": session_id(), "ticking": mode() == "real",
            "real_now": datetime.now(timezone.utc).isoformat(timespec="seconds")}
