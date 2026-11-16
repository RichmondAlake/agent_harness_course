"""Real calendars: a read-only iCal feed, or Google Calendar with write access.

Two providers cover most learners:

``ics``
    The calendar's secret iCal address. Read-only and needs no OAuth client.
    Blocks the assistant creates are kept in a local overlay and can be
    imported into any calendar as an ``.ics`` file.

``google``
    Google Calendar through OAuth. Reads and, after approval, writes.

Both return events in the neutral shape the harness uses everywhere.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ICS_FIELDS = [
    {"name": "ics_url", "label": "Secret iCal address", "type": "password", "required": True,
     "help": "Google Calendar: Settings, your calendar, 'Secret address in iCal format'. "
             "Treat it like a password: anyone holding it can read the calendar."},
]
GOOGLE_FIELDS = [
    {"name": "client_secrets", "label": "OAuth client file", "type": "text", "required": True,
     "help": "Path to the OAuth client JSON for a Desktop app, with the Calendar API enabled."},
    {"name": "calendar_id", "label": "Calendar ID", "type": "text", "required": False,
     "default": "primary", "help": "Use 'primary' for your main calendar."},
]
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
FOCUS_WORDS = ("focus", "deep work", "pomodoro", "do not disturb", "heads down")


def classify(title: str, attendees: list[str], owner: str) -> str:
    """Meeting when other people attend; focus or personal when only the owner does."""
    others = [person for person in attendees if person and person != owner]
    if others:
        return "meeting"
    return "focus" if any(word in title.lower() for word in FOCUS_WORDS) else "personal"


def _moment(value: Any, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=zone)).astimezone(zone)
    return datetime.combine(value, time.min, tzinfo=zone)


def overlay_ics(events: list[dict[str, Any]], product: str = "PPA") -> str:
    """Render overlay events as an iCalendar document for import."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{product}//time blocks//EN"]
    for event in events:
        start = datetime.fromisoformat(event["start"]).astimezone(ZoneInfo("UTC"))
        end = datetime.fromisoformat(event["end"]).astimezone(ZoneInfo("UTC"))
        lines += ["BEGIN:VEVENT", f"UID:{event['event_id']}@ppa.local",
                  f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{end:%Y%m%dT%H%M%SZ}",
                  f"SUMMARY:{event['title']}", "END:VEVENT"]
    return "\r\n".join(lines + ["END:VCALENDAR", ""])


class OverlayMixin:
    """Events the assistant created, kept locally and merged into every listing."""

    def _init_overlay(self) -> None:
        self.overlay: list[dict[str, Any]] = []
        self.responses: dict[str, str] = {}

    def _add_overlay(self, title: str, start: str, end: str, attendees: list[str] | None,
                     description: str, kind: str) -> dict[str, Any]:
        event = {"event_id": f"EV-{uuid.uuid4().hex[:10].upper()}", "title": title, "kind": kind,
                 "start": start, "end": end, "organizer": self.owner_email,
                 "attendees": attendees or [self.owner_email], "location": "",
                 "response": "accepted", "related_thread": None, "related_page": None,
                 "description": description}
        self.overlay.append(event)
        return event


class IcsCalendar(OverlayMixin):
    provider_id = "ics"

    def __init__(self, settings: dict[str, Any], owner_email: str, timezone_name: str) -> None:
        self.url = settings["ics_url"].strip().replace("webcal://", "https://")
        self.owner_email = owner_email
        self.zone = ZoneInfo(timezone_name)
        self._init_overlay()

    def _calendar(self):
        import icalendar
        import requests

        response = requests.get(self.url, timeout=30)
        response.raise_for_status()
        return icalendar.Calendar.from_ical(response.content)

    def check(self) -> dict[str, Any]:
        today = datetime.now(self.zone).date()
        found = self.list_events(today.isoformat(), (today + timedelta(days=7)).isoformat())
        return {"account": "iCal feed", "events_next_7_days": len(found["events"])}

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": "iCal feed",
                "detail": "Read-only feed. Blocks the assistant creates stay in a local overlay."}

    def list_events(self, start_date: str, end_date: str = "") -> dict:
        import recurring_ical_events

        first = date.fromisoformat(start_date[:10])
        last = date.fromisoformat(end_date[:10]) if end_date else first
        window = (datetime.combine(first, time.min, tzinfo=self.zone),
                  datetime.combine(last + timedelta(days=1), time.min, tzinfo=self.zone))
        rows = []
        for item in recurring_ical_events.of(self._calendar()).between(*window):
            start_value, end_value = item["DTSTART"].dt, item.get("DTEND", item["DTSTART"]).dt
            if not isinstance(start_value, datetime):
                continue        # all-day entries do not occupy a time slot
            people = item.get("ATTENDEE", [])
            people = people if isinstance(people, list) else [people]
            attendees = [str(person).replace("mailto:", "").lower() for person in people]
            title = str(item.get("SUMMARY", "(no title)"))
            event_id = str(item.get("UID", uuid.uuid4().hex))
            rows.append({
                "event_id": event_id, "title": title,
                "kind": classify(title, attendees, self.owner_email),
                "start": _moment(start_value, self.zone).isoformat(timespec="minutes"),
                "end": _moment(end_value, self.zone).isoformat(timespec="minutes"),
                "organizer": str(item.get("ORGANIZER", "")).replace("mailto:", "").lower(),
                "attendees": attendees, "location": str(item.get("LOCATION", "")),
                "response": self.responses.get(event_id, "accepted"),
                "related_thread": None, "related_page": None,
                "description": str(item.get("DESCRIPTION", ""))[:1500],
            })
        rows += [item for item in self.overlay
                 if first <= datetime.fromisoformat(item["start"]).date() <= last]
        return {"events": sorted(rows, key=lambda item: item["start"]),
                "timezone": str(self.zone)}

    def create_event(self, title: str, start: str, end: str, attendees: list[str] | None = None,
                     description: str = "", kind: str = "focus") -> dict:
        event = self._add_overlay(title, start, end, attendees, description, kind)
        return {"event_id": event["event_id"], "status": "created_in_overlay", "start": start,
                "end": end, "delivery": "local overlay: the iCal feed is read-only"}

    def respond_to_event(self, event_id: str, response: str, comment: str = "") -> dict:
        self.responses[event_id] = response
        return {"event_id": event_id, "status": response,
                "delivery": "recorded locally: an iCal feed cannot notify the organiser"}

    def delete_event(self, event_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes real events."}


class GoogleCalendar:
    provider_id = "google"

    def __init__(self, settings: dict[str, Any], owner_email: str, timezone_name: str,
                 token_path: Path) -> None:
        self.client_secrets = Path(settings["client_secrets"]).expanduser()
        self.calendar_id = settings.get("calendar_id") or "primary"
        self.owner_email = owner_email
        self.zone = ZoneInfo(timezone_name)
        self.token_path = token_path

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), GOOGLE_SCOPES)
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets), GOOGLE_SCOPES)
            credentials = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        self.token_path.chmod(0o600)
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def check(self) -> dict[str, Any]:
        today = datetime.now(self.zone).date()
        found = self.list_events(today.isoformat(), (today + timedelta(days=7)).isoformat())
        return {"account": self.calendar_id, "events_next_7_days": len(found["events"])}

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": self.calendar_id,
                "detail": "Google Calendar through OAuth, scope calendar.events"}

    def _neutral(self, item: dict[str, Any]) -> dict[str, Any] | None:
        if "dateTime" not in item.get("start", {}):
            return None
        attendees = [person.get("email", "").lower() for person in item.get("attendees", [])]
        mine = next((person for person in item.get("attendees", []) if person.get("self")), {})
        title = item.get("summary", "(no title)")
        return {
            "event_id": item["id"], "title": title,
            "kind": classify(title, attendees, self.owner_email),
            "start": datetime.fromisoformat(item["start"]["dateTime"]).astimezone(self.zone)
            .isoformat(timespec="minutes"),
            "end": datetime.fromisoformat(item["end"]["dateTime"]).astimezone(self.zone)
            .isoformat(timespec="minutes"),
            "organizer": item.get("organizer", {}).get("email", "").lower(),
            "attendees": attendees, "location": item.get("location", ""),
            "response": mine.get("responseStatus", "accepted"),
            "related_thread": None, "related_page": None,
            "description": (item.get("description") or "")[:1500],
        }

    def list_events(self, start_date: str, end_date: str = "") -> dict:
        first = date.fromisoformat(start_date[:10])
        last = date.fromisoformat(end_date[:10]) if end_date else first
        low = datetime.combine(first, time.min, tzinfo=self.zone)
        high = datetime.combine(last + timedelta(days=1), time.min, tzinfo=self.zone)
        found = self._service().events().list(
            calendarId=self.calendar_id, timeMin=low.isoformat(), timeMax=high.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=250).execute()
        rows = [event for event in map(self._neutral, found.get("items", [])) if event]
        return {"events": rows, "timezone": str(self.zone)}

    def create_event(self, title: str, start: str, end: str, attendees: list[str] | None = None,
                     description: str = "", kind: str = "focus") -> dict:
        others = [person for person in attendees or [] if person != self.owner_email]
        body = {"summary": title, "description": description,
                "start": {"dateTime": start}, "end": {"dateTime": end},
                "attendees": [{"email": person} for person in others]}
        created = self._service().events().insert(
            calendarId=self.calendar_id, body=body,
            sendUpdates="all" if others else "none").execute()
        return {"event_id": created["id"], "status": "created", "start": start, "end": end,
                "delivery": "real"}

    def respond_to_event(self, event_id: str, response: str, comment: str = "") -> dict:
        service = self._service()
        event = service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        for person in event.get("attendees", []):
            if person.get("self"):
                person["responseStatus"] = response
                if comment:
                    person["comment"] = comment
        service.events().patch(calendarId=self.calendar_id, eventId=event_id,
                               body={"attendees": event.get("attendees", [])},
                               sendUpdates="all").execute()
        return {"event_id": event_id, "status": response, "delivery": "real"}

    def delete_event(self, event_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes real events."}
