"""One workspace, swappable providers, and the two safety switches around them.

The harness talks to mail, calendar and notes through a single object. Behind
it sit either the practice workspace (a real public mailbox replayed against
a clock) or the owner's real accounts. The harness code is the same either way.

Two rules hold for every provider:

* **Safe mode** (on by default). With real accounts, an approved message
  leaves only when every recipient is the owner. Anything addressed to another
  person is saved as a draft instead. Approval says "this is fine"; safe mode
  says "and I am ready for it to really happen".
* **Effect log**. Every outward action is recorded with what was asked and
  what actually happened, so "approved" and "delivered" are never confused.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from calendars import GOOGLE_FIELDS, ICS_FIELDS, GoogleCalendar, IcsCalendar, OverlayMixin
from contacts import derive_contacts
from imap_mail import FIELDS as IMAP_FIELDS
from imap_mail import ImapMail
from notes import FOLDER_FIELDS, NOTION_FIELDS, FolderNotes, NotionNotes
from practice import PracticeWorkspace
from settings import load_connections, owner_settings, redact, save_connections, store_path
from textutil import display_name

SYSTEMS = ("mail", "calendar", "notes")
CONTACT_CACHE_SECONDS = 600


def local_timezone() -> str:
    """The owner's timezone: ``PPA_TIMEZONE``, else the machine's zone."""
    configured = os.environ.get("PPA_TIMEZONE", "").strip()
    if configured:
        return configured
    link = Path("/etc/localtime")
    if link.is_symlink() and "zoneinfo/" in str(link.resolve()):
        return str(link.resolve()).split("zoneinfo/", 1)[1]
    return "UTC"


class NotConnectedMail:
    """Placeholder used in real mode before a mailbox is connected."""

    provider_id = "none"
    owner_email = ""

    def status(self) -> dict[str, Any]:
        return {"provider": "none", "connected": False, "account": "",
                "detail": "No mailbox connected."}

    def inbox(self) -> list[dict[str, Any]]:
        return []

    def sent_headers(self) -> list[dict[str, Any]]:
        return []

    def search_threads(self, query: str = "", label: str = "INBOX", max_results: int = 25) -> dict:
        return {"threads": [], "note": "No mailbox is connected."}

    def get_thread(self, thread_id: str) -> dict:
        return {"error": "not_connected", "detail": "No mailbox is connected."}

    create_draft = send_message = trash_thread = \
        lambda self, *args, **kwargs: {"error": "not_connected", "detail": "No mailbox is connected."}

    def list_drafts(self) -> dict:
        return {"drafts": []}

    def list_sent(self) -> dict:
        return {"sent": []}


class LocalCalendar(OverlayMixin):
    """A calendar that holds only what the assistant created."""

    provider_id = "local"

    def __init__(self, owner_email: str, timezone_name: str) -> None:
        self.owner_email, self.timezone = owner_email, timezone_name
        self._init_overlay()

    def status(self) -> dict[str, Any]:
        return {"provider": "local", "connected": False, "account": "",
                "detail": "No calendar connected. Time blocks are kept locally."}

    def list_events(self, start_date: str, end_date: str = "") -> dict:
        last = (end_date or start_date)[:10]
        rows = [item for item in self.overlay if start_date[:10] <= item["start"][:10] <= last]
        return {"events": sorted(rows, key=lambda item: item["start"]), "timezone": self.timezone}

    def create_event(self, title: str, start: str, end: str, attendees: list[str] | None = None,
                     description: str = "", kind: str = "focus") -> dict:
        event = self._add_overlay(title, start, end, attendees, description, kind)
        return {"event_id": event["event_id"], "status": "created_in_overlay", "start": start,
                "end": end, "delivery": "local overlay: no calendar is connected"}

    def respond_to_event(self, event_id: str, response: str, comment: str = "") -> dict:
        return {"error": "event_not_found", "event_id": event_id}

    def delete_event(self, event_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes events."}


PROVIDERS: dict[str, list[dict[str, Any]]] = {
    "mail": [
        {"id": "imap", "label": "IMAP and SMTP with an app password",
         "help": "Works with Gmail, Outlook, iCloud and Fastmail. The mailbox is opened "
                 "read-only. Sending is possible only after you approve a specific message.",
         "fields": IMAP_FIELDS},
    ],
    "calendar": [
        {"id": "ics", "label": "Secret iCal address (read-only)",
         "help": "Reads your real calendar. Blocks the assistant creates stay in a local "
                 "overlay that you can import.", "fields": ICS_FIELDS},
        {"id": "google", "label": "Google Calendar (read and write)",
         "help": "Opens a browser window for Google's consent screen. Writes happen only "
                 "after you approve a specific event.", "fields": GOOGLE_FIELDS},
    ],
    "notes": [
        {"id": "notion", "label": "Notion integration",
         "help": "The integration sees only pages you share with it.", "fields": NOTION_FIELDS},
        {"id": "folder", "label": "Folder of Markdown files",
         "help": "For learners who do not use Notion.", "fields": FOLDER_FIELDS},
    ],
}


class Workspace:
    def __init__(self) -> None:
        self.practice = PracticeWorkspace(now=os.environ.get("PPA_PRACTICE_NOW") or None)
        self.safe_mode = os.environ.get("PPA_SAFE_MODE", "1") != "0"
        kept = self.practice.state_path
        self.ledger = kept.with_name(kept.stem + "_effects.json") if kept else None
        self.effects: list[dict[str, Any]] = self._kept_effects()
        self.real: dict[str, Any] = {}
        self._contacts: tuple[float, list[dict[str, Any]]] = (0.0, [])
        for system, saved in load_connections().items():
            try:
                self.real[system] = self._build(system, saved["provider"], saved["settings"])
            except Exception:          # a stale secret must not stop the gateway from starting
                continue

    # ── Providers ────────────────────────────────────────────────────────────

    @property
    def practising(self) -> bool:
        return not self.real

    @property
    def timezone(self) -> str:
        return self.practice.timezone if self.practising else local_timezone()

    @property
    def owner_email(self) -> str:
        if self.practising:
            return self.practice.owner_email
        mail = self.real.get("mail")
        return mail.owner_email if mail else os.environ.get("PPA_OWNER_EMAIL", "")

    def provider(self, system: str) -> Any:
        if self.practising:
            return self.practice
        if system in self.real:
            return self.real[system]
        if system == "mail":
            return NotConnectedMail()
        if system == "calendar":
            return self.real.setdefault("_local_calendar",
                                        LocalCalendar(self.owner_email, self.timezone))
        return FolderNotes({"path": str(store_path().parent / "notes")})

    def _build(self, system: str, provider_id: str, settings: dict[str, Any]) -> Any:
        if (system, provider_id) == ("mail", "imap"):
            return ImapMail(settings, local_timezone())
        owner = settings.get("owner_email") or self.owner_email
        if (system, provider_id) == ("calendar", "ics"):
            return IcsCalendar(settings, owner, local_timezone())
        if (system, provider_id) == ("calendar", "google"):
            return GoogleCalendar(settings, owner, local_timezone(),
                                  store_path().parent / "google-calendar-token.json")
        if (system, provider_id) == ("notes", "notion"):
            return NotionNotes(settings)
        if (system, provider_id) == ("notes", "folder"):
            return FolderNotes(settings)
        raise ValueError(f"Unknown provider '{provider_id}' for {system}")

    def connect(self, system: str, provider_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Test first. Store the settings only when the connection works."""
        if system not in SYSTEMS:
            raise ValueError(f"Unknown system '{system}'")
        provider = self._build(system, provider_id, settings)
        checked = provider.check()
        self.real[system] = provider
        self.real.pop("_local_calendar", None)
        saved = load_connections()
        saved[system] = {"provider": provider_id, "settings": settings}
        save_connections(saved)
        self._contacts = (0.0, [])
        return {"system": system, "checked": checked, **provider.status(),
                "settings": redact(settings)}

    def disconnect(self, system: str) -> dict[str, Any]:
        self.real.pop(system, None)
        if not any(name in self.real for name in SYSTEMS):
            self.real.clear()
        saved = load_connections()
        saved.pop(system, None)
        save_connections(saved)
        self._contacts = (0.0, [])
        return {"system": system, "status": "disconnected", "practising": self.practising}

    # ── Identity and time ────────────────────────────────────────────────────

    def now(self) -> datetime:
        return self.practice.now if self.practising else datetime.now(ZoneInfo(self.timezone))

    def contacts(self) -> list[dict[str, Any]]:
        if self.practising:
            return self.practice.contacts()
        cached_at, cached = self._contacts
        if time.monotonic() - cached_at < CONTACT_CACHE_SECONDS and cached:
            return cached
        headers = self.provider("mail").sent_headers()
        rows = derive_contacts(headers, self.owner_email, self.now())
        self._contacts = (time.monotonic(), rows)
        return rows

    def status(self) -> dict[str, Any]:
        return {
            "status": "ok", "mode": "practice" if self.practising else "real",
            "safe_mode": self.safe_mode,
            "owner": {"name": display_name(self.owner_email) if self.owner_email else "",
                      "email": self.owner_email, "timezone": self.timezone},
            "systems": {name: self.provider(name).status() for name in SYSTEMS},
            "clock": self.now().isoformat(timespec="minutes"),
            "clock_is_pinned": self.practising,
        }

    def world(self) -> dict[str, Any]:
        persona = {"user_id": (self.owner_email or "owner").split("@")[0].replace(".", "-"),
                   "name": display_name(self.owner_email) if self.owner_email else "Owner",
                   "email": self.owner_email, "timezone": self.timezone, **owner_settings()}
        return {"persona": persona, "contacts": self.contacts(),
                "scenario_now": self.now().isoformat(timespec="minutes") if self.practising else None,
                "anchor_day": self.now().date().isoformat(), "mode": self.status()["mode"],
                "provenance": self.practice.meta if self.practising else None}

    # ── Effects ──────────────────────────────────────────────────────────────

    def _kept_effects(self) -> list[dict[str, Any]]:
        """The ledger as it was when the gateway last stopped. Empty when nothing is kept."""
        if self.ledger is None or not self.ledger.exists():
            return []
        try:
            return json.loads(self.ledger.read_text())
        except (OSError, ValueError):
            return []

    def keep_effects(self) -> None:
        if self.ledger is not None:
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            self.ledger.write_text(json.dumps(self.effects, indent=1, default=str))

    def _record(self, kind: str, request: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
        self.effects.append({"effect_id": uuid.uuid4().hex[:12], "kind": kind,
                             "at": self.now().isoformat(timespec="seconds"),
                             "mode": "practice" if self.practising else "real",
                             "safe_mode": self.safe_mode, "request": request, "outcome": outcome})
        self.keep_effects()
        return outcome

    def send_message(self, to: list[str], subject: str, body: str, thread_id: str = "",
                     cc: list[str] | None = None) -> dict[str, Any]:
        mail = self.provider("mail")
        others = sorted({item.lower() for item in to + (cc or [])} - {self.owner_email})
        request = {"to": to, "cc": cc or [], "subject": subject, "thread_id": thread_id}
        if not self.practising and self.safe_mode and others:
            draft = mail.create_draft(to, subject, body, thread_id)
            return self._record("mail_send_message", request, {
                "status": "held_by_safe_mode", "delivered": False,
                "draft_id": draft.get("draft_id"), "held_for": others,
                "detail": "Safe mode is on, so the message was saved as a draft. "
                          "Turn safe mode off to send to other people."})
        outcome = mail.send_message(to, subject, body, thread_id, cc)
        return self._record("mail_send_message", request,
                            dict(outcome, delivered=outcome.get("status") == "sent"))

    def create_event(self, title: str, start: str, end: str, attendees: list[str] | None = None,
                     description: str = "", kind: str = "focus") -> dict[str, Any]:
        others = sorted({item.lower() for item in attendees or []} - {self.owner_email})
        request = {"title": title, "start": start, "end": end, "attendees": attendees or []}
        invited = attendees
        removed: list[str] = []
        if not self.practising and self.safe_mode and others:
            invited, removed = [self.owner_email], others
        outcome = self.provider("calendar").create_event(title, start, end, invited, description, kind)
        if removed:
            outcome = dict(outcome, attendees_removed=removed,
                           detail="Safe mode is on, so nobody else was invited.")
        return self._record("calendar_create_event", request, outcome)

    def respond_to_event(self, event_id: str, response: str, comment: str = "") -> dict[str, Any]:
        request = {"event_id": event_id, "response": response}
        if response not in {"accepted", "declined", "tentative"}:
            return {"error": "invalid_response", "allowed": ["accepted", "declined", "tentative"]}
        if not self.practising and self.safe_mode:
            return self._record("calendar_respond_to_event", request, {
                "status": "held_by_safe_mode", "delivered": False,
                "detail": "Safe mode is on, so the organiser was not notified."})
        outcome = self.provider("calendar").respond_to_event(event_id, response, comment)
        return self._record("calendar_respond_to_event", request, outcome)

    def append_to_page(self, page_id: str, text: str) -> dict[str, Any]:
        notes = self.provider("notes")
        page = notes.get_page(page_id).get("page")
        if page is None:
            return {"error": "page_not_found", "page_id": page_id}
        if not page["shared"]:
            return notes.append_to_page(page_id, text)
        request = {"page_id": page_id, "characters": len(text)}
        if not self.practising and self.safe_mode:
            return self._record("notes_append_to_page", request, {
                "status": "held_by_safe_mode", "delivered": False,
                "detail": "Safe mode is on, so the shared page was not changed."})
        return self._record("notes_append_to_page", request, notes.append_to_page(page_id, text))
