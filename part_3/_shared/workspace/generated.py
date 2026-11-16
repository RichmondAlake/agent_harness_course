"""A generated layer of working sessions for the practice calendar.

Invitations that travel by email are only part of a calendar. The calendar
derived from the practice mailbox is real, and too quiet to be a fair test. This
module fills the week by one rule:

    For each week, take the threads the owner wrote on most during the fortnight
    before, and give each one a working session in a fixed weekly pattern.

Every generated event says so (``source`` is ``generated``), points at the real
thread it came from, and lists the owner as its only attendee: no real person is
placed in a meeting that never happened. An event that came from an invitation
always wins. A generated session that overlaps one is dropped.

The layer is opt-in. Pass ``generated_calendar=True`` to ``PracticeWorkspace`` or
set ``PPA_GENERATED_CALENDAR=1``.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from textutil import SUBJECT_PREFIX, thread_id_for

UTC = ZoneInfo("UTC")
# (weekday, start, minutes). Thursday is heavy on purpose: it breaks the over-booked rule.
PATTERN = [(0, "11:00", 60), (1, "11:00", 60), (1, "14:30", 30), (2, "10:30", 60),
           (3, "10:30", 60), (3, "13:00", 90), (3, "15:00", 120), (4, "14:00", 60)]


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def monday_of(moment: datetime) -> datetime:
    day = moment.date() - timedelta(days=moment.weekday())
    return datetime.combine(day, time(0), moment.tzinfo)


def generated_week(sent: list[dict[str, Any]], monday: datetime,
                   owner_email: str) -> list[dict[str, Any]]:
    """One working session for each thread the owner wrote on most in the fortnight before."""
    low, high = _stamp(monday - timedelta(days=14)), _stamp(monday)
    counts: Counter[str] = Counter()
    subjects: dict[str, str] = {}
    for message in sorted(sent, key=lambda item: item["stamp"]):
        if low <= message["stamp"] < high:
            key = thread_id_for(message["subject"], message["message_id"])
            counts[key] += 1
            subjects[key] = message["subject"] or ""
    busiest = sorted(counts, key=lambda key: (-counts[key], key))[:len(PATTERN)]
    week = []
    for thread, (weekday, clock, minutes) in zip(busiest, PATTERN):
        start = datetime.combine(monday.date() + timedelta(days=weekday),
                                 time.fromisoformat(clock), monday.tzinfo)
        matter = " ".join(SUBJECT_PREFIX.sub("", subjects[thread]).split()) or "open matter"
        week.append({
            "event_id": f"EV-G{start:%m%d%H}", "kind": "meeting",
            "title": "Working session: " + matter[:60],
            "start": start.isoformat(timespec="minutes"),
            "end": (start + timedelta(minutes=minutes)).isoformat(timespec="minutes"),
            "organizer": owner_email, "attendees": [owner_email], "location": "",
            "response": "accepted", "related_thread": thread, "related_page": None,
            "description": "Generated working session. It did not come from an invitation.",
            "announced_at": _stamp(monday - timedelta(days=3) + timedelta(hours=17)),
            "source": "generated",
        })
    return week


def overlaps(one: dict[str, Any], other: dict[str, Any]) -> bool:
    return (datetime.fromisoformat(one["start"]) < datetime.fromisoformat(other["end"])
            and datetime.fromisoformat(other["start"]) < datetime.fromisoformat(one["end"]))


def generated_layer(sent: list[dict[str, Any]], invitations: list[dict[str, Any]],
                    anchor: datetime, owner_email: str, weeks: int = 2) -> list[dict[str, Any]]:
    """Generated sessions for the anchor week and the weeks after it, invitations excluded."""
    first = monday_of(anchor)
    layer = [event for index in range(weeks)
             for event in generated_week(sent, first + timedelta(days=7 * index), owner_email)]
    return [event for event in layer if not any(overlaps(event, real) for real in invitations)]


def visible(layer: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Only sessions that have been announced by now."""
    return [event for event in layer if event["announced_at"] <= _stamp(now)]


__all__ = ["PATTERN", "generated_layer", "generated_week", "monday_of", "overlaps", "visible"]
