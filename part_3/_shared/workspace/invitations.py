"""Turn meeting invitations found in email into calendar events.

Outlook writes the schedule into the message body:

    When: Tuesday, August 07, 2001 9:00 AM-9:30 AM (GMT-06:00) Central Time (US & Canada).
    Where: EB 3567

An "Updated:" message replaces the earlier invitation with the same title and
organiser. A "Canceled:" message removes it. Only invitations that had already
arrived by ``now`` count: nobody can attend a meeting they have not heard of.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from textutil import clip, normalise_subject, short_id, thread_id_for

WHEN = re.compile(
    r"When:\s+\w+, (?P<day>\w+ \d{1,2}, \d{4}) (?P<start>\d{1,2}:\d{2} [AP]M)-"
    r"(?P<end>\d{1,2}:\d{2} [AP]M)\s*(?:\((?P<zone>[^)]*)\)\s*(?P<label>[^.\n]*))?")
WHERE = re.compile(r"^Where:[ \t]*(?P<place>.*)$", re.M)
SEPARATOR = re.compile(r"\*~\*~[*~]+")

# Windows time-zone labels as Outlook prints them, mapped to IANA names.
WINDOWS_ZONES = {
    "central time (us & canada)": "America/Chicago",
    "eastern time (us & canada)": "America/New_York",
    "mountain time (us & canada)": "America/Denver",
    "pacific time (us & canada)": "America/Los_Angeles",
    "greenwich mean time : dublin, edinburgh, lisbon, london": "Europe/London",
}


def is_invitation(body: str) -> bool:
    return bool(WHEN.search(body[:400]))


def zone_name(body: str, default: str = "UTC") -> str:
    match = WHEN.search(body[:400])
    label = (match["label"] or "").strip().lower() if match else ""
    return WINDOWS_ZONES.get(label, default)


def parse_invitation(message: dict[str, Any], default_zone: str) -> dict[str, Any] | None:
    """Parse one message into an event, or return ``None`` when it is not one."""
    match = WHEN.search(message["body"][:400])
    if not match:
        return None
    zone = ZoneInfo(zone_name(message["body"], default_zone))
    try:
        start = datetime.strptime(f"{match['day']} {match['start']}", "%B %d, %Y %I:%M %p")
        end = datetime.strptime(f"{match['day']} {match['end']}", "%B %d, %Y %I:%M %p")
    except ValueError:
        return None
    place = WHERE.search(message["body"])
    parts = SEPARATOR.split(message["body"], maxsplit=1)
    subject = message["subject"] or ""
    title = re.sub(r"(?i)^\s*(updated|canceled|cancelled)\s*:\s*", "", subject).strip()
    return {
        "event_id": short_id("EV", normalise_subject(subject) + "|" + message["sender"]),
        "title": title or "(no title)",
        "kind": "meeting",
        "start": start.replace(tzinfo=zone).isoformat(timespec="minutes"),
        "end": end.replace(tzinfo=zone).isoformat(timespec="minutes"),
        "organizer": message["sender"],
        "attendees": sorted({message["sender"], *message["recipients"], *message["cc"]}),
        "location": place["place"].strip() if place else "",
        "response": "needsAction",
        "related_thread": thread_id_for(subject, message["message_id"]),
        "related_page": None,
        "description": clip(parts[1].strip(), 1500) if len(parts) > 1 else "",
        "cancelled": bool(re.match(r"(?i)^\s*cancell?ed\s*:", subject)),
        "announced_at": message["stamp"],
        "source": "invitation",
    }


def events_from_messages(messages: list[dict[str, Any]], now: datetime,
                         default_zone: str) -> list[dict[str, Any]]:
    """Apply invitations, updates and cancellations in arrival order."""
    known_until = now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    current: dict[str, dict[str, Any]] = {}
    for message in sorted(messages, key=lambda item: item["stamp"]):
        if message["stamp"] > known_until:
            break
        event = parse_invitation(message, default_zone)
        if event is None:
            continue
        if event.pop("cancelled"):
            current.pop(event["event_id"], None)
        else:
            current[event["event_id"]] = event
    return sorted(current.values(), key=lambda item: item["start"])
