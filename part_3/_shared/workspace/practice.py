"""The practice workspace: a real public mailbox, replayed against a clock.

Source data is the slice built by ``data/build_practice_slice.py`` from the
Enron email corpus and Microsoft's LLMail-Inject challenge. Nothing here is
invented. The practice workspace exists for learners who prefer not to connect
their own accounts, and for tests that must be repeatable.

Time is the interesting part. Every message carries its real timestamp, so
moving the clock forward makes mail arrive and meetings get announced, exactly
as they did. The assistant never sees a message from its own future.

What the assistant writes (drafts, sent mail, events, answers to invitations,
pages) is held in memory. Give the workspace a ``state_path``, or set
``PPA_PRACTICE_STATE``, and the same writes are kept in that file, so they are
still there after the process that serves the workspace is started again.
"""
from __future__ import annotations

import gzip
import json
import os
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from contacts import derive_contacts
from generated import generated_layer, visible
from invitations import events_from_messages, is_invitation, parse_invitation, zone_name
from textutil import clip, display_name, normalise_subject, snippet, thread_id_for

SLICE = Path(__file__).resolve().parents[1] / "data" / "practice_slice.json.gz"
BULK_RECIPIENTS = 15
UTC = ZoneInfo("UTC")
WRITTEN = ("drafts", "outbox", "trashed", "created", "removed", "responses", "pages")


def stamp_of(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def moment_of(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class PracticeWorkspace:
    """Mail, calendar and notes for one real mailbox at one moment in time."""

    provider_id = "practice"

    def __init__(self, slice_path: Path | None = None, now: str | None = None,
                 inbox_days: int = 5, generated_calendar: bool | None = None,
                 state_path: Path | str | None = None) -> None:
        kept = state_path or os.environ.get("PPA_PRACTICE_STATE")
        self.state_path = Path(kept) if kept else None
        raw = json.loads(gzip.decompress((slice_path or SLICE).read_bytes()))
        self.meta = raw["meta"]
        self.owner_email = self.meta["owner_email"]
        self.sent = raw["sent"]
        self.benign_probe = raw["benign_probe"]
        self.inbox_days = inbox_days
        zones = Counter(zone_name(item["body"]) for item in raw["received"]
                        if is_invitation(item["body"]))
        self.timezone = zones.most_common(1)[0][0] if zones else "UTC"
        self.zone = ZoneInfo(self.timezone)
        self.default_now = self._parse_now(now or self.meta["scenario"]["now"])
        self.now = self.default_now
        self.received = sorted(raw["received"] + self._injections(raw["injections"]),
                               key=lambda item: item["stamp"])
        if generated_calendar is None:
            generated_calendar = os.environ.get("PPA_GENERATED_CALENDAR", "0") == "1"
        self.generated_calendar = generated_calendar
        self.generated = self._generated_layer() if generated_calendar else []
        self.reset(keep=True)
        self._load()

    # ── Clock ────────────────────────────────────────────────────────────────

    def _parse_now(self, value: str) -> datetime:
        moment = datetime.fromisoformat(value)
        return moment if moment.tzinfo else moment.replace(tzinfo=self.zone)

    def set_clock(self, value: str | None) -> datetime:
        self.now = self._parse_now(value) if value else self.default_now
        return self.now

    def reset(self, keep: bool = False) -> None:
        self.now = self.default_now
        self.drafts: list[dict[str, Any]] = []
        self.outbox: list[dict[str, Any]] = []
        self.trashed: set[str] = set()
        self.created: list[dict[str, Any]] = []
        self.removed: set[str] = set()
        self.responses: dict[str, str] = {}
        self.pages: list[dict[str, Any]] = []
        if not keep:
            self._save()

    # ── What was written ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Bring back what was written before the process was last stopped."""
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            kept = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return                      # an unreadable file must not stop the workspace
        for name in WRITTEN:
            if name in kept:
                setattr(self, name, set(kept[name]) if name in {"trashed", "removed"} else kept[name])

    def _save(self) -> None:
        if self.state_path is None:
            return
        kept = {name: sorted(getattr(self, name)) if name in {"trashed", "removed"}
                else getattr(self, name) for name in WRITTEN}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        draft = self.state_path.with_suffix(".writing")
        draft.write_text(json.dumps(kept, indent=1))
        draft.replace(self.state_path)

    def _injections(self, attacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Place each real attack email in the inbox, a day apart, before ``now``."""
        rows = []
        for index, attack in enumerate(attacks):
            arrived = self.default_now - timedelta(hours=7 + 24 * index, minutes=13 * index)
            rows.append({
                "message_id": f"<{attack['source_sha256'][:24]}@llmail-inject.invalid>",
                "subject": attack["subject"], "body": attack["body"],
                "sender": f"{attack['source_sha256'][:10]}@llmail-inject.invalid",
                "recipients": [self.owner_email], "cc": [], "folder": "inbox",
                "stamp": stamp_of(arrived), "origin": "microsoft/llmail-inject-challenge",
            })
        return rows

    # ── Mail ─────────────────────────────────────────────────────────────────

    def _labels(self, message: dict[str, Any]) -> list[str]:
        labels = ["INBOX"]
        everyone = message["recipients"] + message["cc"]
        if is_invitation(message["body"]):
            labels.append("CALENDAR")
        if len(everyone) >= BULK_RECIPIENTS or self.owner_email not in everyone:
            labels.append("BULK")
        elif self.owner_email in message["recipients"]:
            labels.append("DIRECT")
        else:
            labels.append("CC")
        return labels

    def _as_mail(self, message: dict[str, Any], count: int = 1) -> dict[str, Any]:
        return {
            "thread_id": thread_id_for(message["subject"], message["message_id"]),
            "message_id": message["message_id"],
            "from_name": display_name(message["sender"]), "from_email": message["sender"],
            "to": message["recipients"], "cc": message["cc"],
            "subject": message["subject"] or "(no subject)",
            "received_at": moment_of(message["stamp"]).astimezone(self.zone).isoformat(timespec="minutes"),
            "labels": self._labels(message), "snippet": snippet(message["body"]),
            "body": clip(message["body"]), "message_count": count,
        }

    def _visible(self, label: str) -> list[dict[str, Any]]:
        high = stamp_of(self.now)
        low = stamp_of(self.now - timedelta(days=self.inbox_days)) if label == "INBOX" else ""
        pool = self.sent if label == "SENT" else self.received
        rows = [item for item in pool if low < item["stamp"] <= high]
        if label == "ALL":
            rows += [item for item in self.sent if item["stamp"] <= high]
        return rows

    def inbox(self) -> list[dict[str, Any]]:
        """The newest message of every thread that reached the inbox window."""
        threads: dict[str, list[dict[str, Any]]] = {}
        for message in self._visible("INBOX"):
            threads.setdefault(thread_id_for(message["subject"], message["message_id"]), []).append(message)
        rows = [self._as_mail(items[-1], len(items)) for key, items in threads.items()
                if key not in self.trashed]
        return sorted(rows, key=lambda row: row["received_at"], reverse=True)

    def search_threads(self, query: str = "", label: str = "INBOX", max_results: int = 25) -> dict:
        words = query.lower().split()
        threads: dict[str, list[dict[str, Any]]] = {}
        for message in self._visible(label if label in {"INBOX", "SENT", "ALL"} else "INBOX"):
            text = f"{message['subject']} {message['body']} {message['sender']}".lower()
            if all(word in text for word in words):
                threads.setdefault(thread_id_for(message["subject"], message["message_id"]), []).append(message)
        rows = [self._as_mail(sorted(items, key=lambda item: item["stamp"])[-1], len(items))
                for key, items in threads.items() if key not in self.trashed]
        rows.sort(key=lambda row: row["received_at"], reverse=True)
        return {"threads": [{key: value for key, value in row.items() if key != "body"}
                            for row in rows[:max(1, min(max_results, 50))]]}

    def get_thread(self, thread_id: str) -> dict:
        history = [item for item in self._visible("ALL")
                   if thread_id_for(item["subject"], item["message_id"]) == thread_id]
        if not history or thread_id in self.trashed:
            return {"error": "thread_not_found", "thread_id": thread_id}
        history.sort(key=lambda item: item["stamp"])
        latest = next((item for item in reversed(history) if item["sender"] != self.owner_email),
                      history[-1])
        thread = self._as_mail(latest, len(history))
        thread["messages"] = [{
            "from_email": item["sender"], "to": item["recipients"], "cc": item["cc"],
            "sent_at": moment_of(item["stamp"]).astimezone(self.zone).isoformat(timespec="minutes"),
            "body": clip(item["body"], 6000)} for item in history]
        people = {person for item in history
                  for person in (item["sender"], *item["recipients"], *item["cc"])}
        return {"thread": thread, "participants": sorted(people)}

    def create_draft(self, to: list[str], subject: str, body: str, thread_id: str = "") -> dict:
        draft = {"draft_id": f"draft-{uuid.uuid4().hex[:10]}", "thread_id": thread_id or None,
                 "to": to, "subject": subject, "body": body}
        self.drafts.append(draft)
        self._save()
        return {"draft_id": draft["draft_id"], "status": "saved_as_draft", "sent": False}

    def send_message(self, to: list[str], subject: str, body: str, thread_id: str = "",
                     cc: list[str] | None = None) -> dict:
        message = {"message_id": f"sent-{uuid.uuid4().hex[:10]}", "thread_id": thread_id or None,
                   "to": to, "cc": cc or [], "subject": subject, "body": body}
        self.outbox.append(message)
        self._save()
        return {"message_id": message["message_id"], "status": "sent", "to": to,
                "delivery": "simulated: the practice workspace has no real recipients"}

    def list_drafts(self) -> dict:
        return {"drafts": self.drafts}

    def list_sent(self) -> dict:
        return {"sent": self.outbox}

    def trash_thread(self, thread_id: str) -> dict:
        self.trashed.add(thread_id)
        self._save()
        return {"thread_id": thread_id, "status": "trashed"}

    def sent_headers(self) -> list[dict[str, Any]]:
        return [item for item in self.sent if item["stamp"] <= stamp_of(self.now)]

    # ── Calendar ─────────────────────────────────────────────────────────────

    def _generated_layer(self) -> list[dict[str, Any]]:
        """Working sessions that fill the scenario fortnight. An invitation always wins."""
        parsed = (parse_invitation(item, self.timezone) for item in self.received + self.sent)
        invitations = [event for event in parsed if event is not None]
        return generated_layer(self.sent, invitations, self.default_now, self.owner_email)

    def _events(self) -> list[dict[str, Any]]:
        announced = events_from_messages(self.received + self.sent, self.now, self.timezone)
        announced += visible(self.generated, self.now)
        rows = [dict(item, response=self.responses.get(item["event_id"], item["response"]))
                for item in announced + self.created if item["event_id"] not in self.removed]
        return sorted(rows, key=lambda item: item["start"])

    def list_events(self, start_date: str, end_date: str = "") -> dict:
        first = date.fromisoformat(start_date[:10])
        last = date.fromisoformat(end_date[:10]) if end_date else first
        rows = [item for item in self._events()
                if first <= datetime.fromisoformat(item["start"]).date() <= last]
        return {"events": rows, "timezone": self.timezone}

    def create_event(self, title: str, start: str, end: str, attendees: list[str] | None = None,
                     description: str = "", kind: str = "focus") -> dict:
        event = {"event_id": f"EV-{uuid.uuid4().hex[:10].upper()}", "title": title, "kind": kind,
                 "start": start, "end": end, "organizer": self.owner_email,
                 "attendees": attendees or [self.owner_email], "location": "",
                 "response": "accepted", "related_thread": None, "related_page": None,
                 "description": description, "announced_at": stamp_of(self.now)}
        self.created.append(event)
        self._save()
        return {"event_id": event["event_id"], "status": "created", "start": start, "end": end}

    def respond_to_event(self, event_id: str, response: str, comment: str = "") -> dict:
        if not any(item["event_id"] == event_id for item in self._events()):
            return {"error": "event_not_found", "event_id": event_id}
        self.responses[event_id] = response
        self._save()
        return {"event_id": event_id, "status": response, "comment": comment,
                "delivery": "simulated: the practice workspace has no real organiser"}

    def delete_event(self, event_id: str) -> dict:
        self.removed.add(event_id)
        self._save()
        return {"event_id": event_id, "status": "deleted"}

    # ── Notes ────────────────────────────────────────────────────────────────

    def _page(self, page_id: str) -> dict[str, Any] | None:
        return next((item for item in self.pages if item["page_id"] == page_id), None)

    def search_pages(self, query: str = "") -> dict:
        words = query.lower().split()
        rows = [{key: page[key] for key in ("page_id", "title", "shared", "last_edited")}
                for page in self.pages
                if not words or any(word in f"{page['title']} {page['body']}".lower() for word in words)]
        return {"pages": rows}

    def get_page(self, page_id: str) -> dict:
        page = self._page(page_id)
        return {"page": page} if page else {"error": "page_not_found", "page_id": page_id}

    def create_page(self, title: str, body: str) -> dict:
        page = {"page_id": f"page-{uuid.uuid4().hex[:10]}", "title": title, "shared": False,
                "last_edited": self.now.isoformat(timespec="minutes"), "body": body}
        self.pages.append(page)
        self._save()
        return {"page_id": page["page_id"], "status": "created", "shared": False}

    def append_to_page(self, page_id: str, text: str) -> dict:
        page = self._page(page_id)
        if page is None:
            return {"error": "page_not_found", "page_id": page_id}
        page["body"] = page["body"].rstrip() + "\n\n" + text.strip() + "\n"
        page["last_edited"] = self.now.isoformat(timespec="minutes")
        self._save()
        return {"page_id": page_id, "status": "updated", "shared": page["shared"]}

    def share_page(self, page_id: str, email: str) -> dict:
        page = self._page(page_id)
        if page is None:
            return {"error": "page_not_found", "page_id": page_id}
        page["shared"] = True
        self._save()
        return {"page_id": page_id, "status": "shared", "with": email}

    def delete_page(self, page_id: str) -> dict:
        self.pages = [item for item in self.pages if item["page_id"] != page_id]
        self._save()
        return {"page_id": page_id, "status": "deleted"}

    # ── Identity ─────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": self.owner_email,
                "detail": (f"Public mailbox '{self.meta['mailbox']}' from "
                           f"{self.meta['sources']['mail']['dataset']}, clock at "
                           f"{self.now.isoformat(timespec='minutes')}")}

    def contacts(self) -> list[dict[str, Any]]:
        return derive_contacts(self.sent_headers(), self.owner_email, self.now)
