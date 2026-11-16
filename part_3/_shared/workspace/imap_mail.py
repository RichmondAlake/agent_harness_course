"""A real mailbox over IMAP and SMTP, using only the standard library.

IMAP with an app password works with Gmail, Outlook, iCloud, Fastmail and most
other providers, and needs no cloud console project. The provider is careful
by construction:

* the mailbox is opened read-only and bodies are fetched with ``BODY.PEEK``,
  so reading never marks a message as seen;
* it never deletes or moves mail;
* it sends only through ``send_message``, which the harness gates behind a
  human approval and the gateway gates again behind safe mode.
"""
from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from invitations import is_invitation
from textutil import clip, display_name, html_to_text, snippet, thread_id_for

FIELDS = [
    {"name": "address", "label": "Email address", "type": "text", "required": True,
     "help": "The mailbox the assistant reads."},
    {"name": "password", "label": "App password", "type": "password", "required": True,
     "help": "An app password, not your account password. Gmail: Google Account, "
             "Security, 2-Step Verification, App passwords."},
    {"name": "imap_host", "label": "IMAP host", "type": "text", "required": True,
     "default": "imap.gmail.com", "help": "imap.gmail.com, outlook.office365.com, imap.mail.me.com"},
    {"name": "smtp_host", "label": "SMTP host", "type": "text", "required": True,
     "default": "smtp.gmail.com", "help": "smtp.gmail.com, smtp.office365.com, smtp.mail.me.com"},
    {"name": "smtp_port", "label": "SMTP port", "type": "number", "required": True, "default": 465,
     "help": "465 for implicit TLS, 587 for STARTTLS."},
    {"name": "inbox_days", "label": "Days of inbox to read", "type": "number", "required": False,
     "default": 5, "help": "Keeps the first read small."},
]
MAX_MESSAGES = 150


def _body_of(message: email.message.Message) -> tuple[str, bool]:
    """Return readable text and whether the message carries a calendar part."""
    plain, rich, calendar = "", "", False
    for part in message.walk():
        kind = part.get_content_type()
        if kind == "text/calendar":
            calendar = True
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        try:
            text = part.get_content()
        except (LookupError, UnicodeDecodeError):
            text = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if kind == "text/plain" and not plain:
            plain = text
        elif kind == "text/html" and not rich:
            rich = text
    return (plain or html_to_text(rich)).strip(), calendar


class ImapMail:
    provider_id = "imap"

    def __init__(self, settings: dict[str, Any], timezone_name: str) -> None:
        self.address = settings["address"].strip().lower()
        self.password = settings["password"]
        self.imap_host = settings["imap_host"].strip()
        self.smtp_host = settings["smtp_host"].strip()
        self.smtp_port = int(settings.get("smtp_port") or 465)
        self.inbox_days = int(settings.get("inbox_days") or 5)
        self.zone = ZoneInfo(timezone_name)
        self.owner_email = self.address
        self.sent_by_gateway: list[dict[str, Any]] = []
        self.saved_drafts: list[dict[str, Any]] = []
        self._cache: dict[str, list[dict[str, Any]]] = {}

    # ── Connection ───────────────────────────────────────────────────────────

    def _open(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self.imap_host, 993, ssl_context=ssl.create_default_context(),
                                   timeout=30)
        client.login(self.address, self.password)
        return client

    def check(self) -> dict[str, Any]:
        client = self._open()
        try:
            status, data = client.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("The INBOX could not be opened read-only.")
            return {"account": self.address, "messages_in_inbox": int(data[0] or 0)}
        finally:
            client.logout()

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "connected": True, "account": self.address,
                "detail": f"IMAP {self.imap_host}, read-only, last {self.inbox_days} days"}

    def _folder(self, client: imaplib.IMAP4_SSL, flag: str, fallback: str) -> str:
        """Find a special-use folder such as ``\\Sent`` or ``\\Drafts``."""
        status, rows = client.list()
        for row in rows if status == "OK" else []:
            text = row.decode("utf-8", errors="replace")
            if flag in text:
                return text.rsplit(' "', 1)[-1].strip('"') if text.endswith('"') else text.split()[-1]
        return fallback

    # ── Reading ──────────────────────────────────────────────────────────────

    def _fetch(self, folder: str, days: int, criteria: str = "") -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        client = self._open()
        try:
            client.select(f'"{folder}"', readonly=True)
            status, data = client.uid("SEARCH", None, f"(SINCE {since}{criteria})")
            uids = data[0].split()[-MAX_MESSAGES:] if status == "OK" and data[0] else []
            rows = []
            for uid in uids:
                status, parts = client.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                flags = parts[0][0].decode("utf-8", errors="replace")
                rows.append(self._parse(parts[0][1], flags, folder))
            return rows
        finally:
            client.logout()

    def _parse(self, raw: bytes, flags: str, folder: str) -> dict[str, Any]:
        message = email.message_from_bytes(raw, policy=default_policy)
        body, has_calendar = _body_of(message)
        sender = (getaddresses([message.get("From", "")]) or [("", "")])[0]
        recipients = [address.lower() for _, address in getaddresses(message.get_all("To", [])) if address]
        copied = [address.lower() for _, address in getaddresses(message.get_all("Cc", [])) if address]
        try:
            received = parsedate_to_datetime(message.get("Date", ""))
        except (TypeError, ValueError):
            received = datetime.now(timezone.utc)
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        subject = str(message.get("Subject", "") or "")
        labels = ["SENT" if folder != "INBOX" else "INBOX"]
        if has_calendar or is_invitation(body):
            labels.append("CALENDAR")
        bulk = any(message.get(name) for name in ("List-Unsubscribe", "List-Id")) or \
            str(message.get("Precedence", "")).lower() in {"bulk", "list", "junk"}
        if bulk or len(recipients + copied) >= 15 or self.address not in recipients + copied:
            labels.append("BULK")
        else:
            labels.append("DIRECT" if self.address in recipients else "CC")
        if "\\Seen" not in flags:
            labels.append("UNREAD")
        message_id = str(message.get("Message-ID", "") or subject)
        return {
            "thread_id": thread_id_for(subject, message_id), "message_id": message_id,
            "from_name": sender[0] or display_name(sender[1]), "from_email": sender[1].lower(),
            "to": recipients, "cc": copied, "subject": subject or "(no subject)",
            "received_at": received.astimezone(self.zone).isoformat(timespec="minutes"),
            "labels": labels, "snippet": snippet(body), "body": clip(body), "message_count": 1,
        }

    def _threads(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in sorted(rows, key=lambda item: item["received_at"]):
            grouped.setdefault(row["thread_id"], []).append(row)
        self._cache.update(grouped)
        newest = [dict(items[-1], message_count=len(items)) for items in grouped.values()]
        return sorted(newest, key=lambda item: item["received_at"], reverse=True)

    def inbox(self) -> list[dict[str, Any]]:
        return self._threads(self._fetch("INBOX", self.inbox_days))

    def search_threads(self, query: str = "", label: str = "INBOX", max_results: int = 25) -> dict:
        words = " ".join(f'TEXT "{word}"' for word in query.replace('"', "").split()[:6])
        folder, days = "INBOX", self.inbox_days
        if label in {"SENT", "ALL"}:
            days = 90
        if label == "SENT":
            client = self._open()
            try:
                folder = self._folder(client, "\\Sent", "Sent")
            finally:
                client.logout()
        rows = self._threads(self._fetch(folder, days, f" {words}" if words else ""))
        return {"threads": [{key: value for key, value in row.items() if key != "body"}
                            for row in rows[:max(1, min(max_results, 50))]]}

    def get_thread(self, thread_id: str) -> dict:
        if thread_id not in self._cache:
            self.inbox()
        items = self._cache.get(thread_id)
        if not items:
            return {"error": "thread_not_found", "thread_id": thread_id}
        thread = dict(items[-1], message_count=len(items))
        thread["messages"] = [{"from_email": item["from_email"], "to": item["to"], "cc": item["cc"],
                               "sent_at": item["received_at"], "body": clip(item["body"], 6000)}
                              for item in items]
        people = {person for item in items for person in (item["from_email"], *item["to"], *item["cc"])}
        return {"thread": thread, "participants": sorted(people)}

    def sent_headers(self) -> list[dict[str, Any]]:
        """Recent sent mail in the neutral shape that contact derivation expects."""
        client = self._open()
        try:
            folder = self._folder(client, "\\Sent", "Sent")
        finally:
            client.logout()
        rows = self._fetch(folder, 90)
        return [{"sender": self.address, "recipients": row["to"], "cc": row["cc"],
                 "stamp": datetime.fromisoformat(row["received_at"]).astimezone(timezone.utc)
                 .strftime("%Y-%m-%dT%H:%M:%SZ")} for row in rows]

    # ── Writing ──────────────────────────────────────────────────────────────

    def _compose(self, to: list[str], subject: str, body: str, cc: list[str] | None) -> EmailMessage:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.address, ", ".join(to), subject
        if cc:
            message["Cc"] = ", ".join(cc)
        message.set_content(body)
        return message

    def create_draft(self, to: list[str], subject: str, body: str, thread_id: str = "") -> dict:
        message = self._compose(to, subject, body, None)
        client = self._open()
        try:
            folder = self._folder(client, "\\Drafts", "Drafts")
            status, _ = client.append(f'"{folder}"', "(\\Draft)", None, message.as_bytes())
        finally:
            client.logout()
        if status != "OK":
            return {"error": "draft_not_saved", "detail": "The server refused the draft."}
        draft = {"draft_id": f"draft-{len(self.saved_drafts) + 1}", "thread_id": thread_id or None,
                 "to": to, "subject": subject, "body": body, "folder": folder}
        self.saved_drafts.append(draft)
        return {"draft_id": draft["draft_id"], "status": "saved_as_draft", "sent": False,
                "folder": folder}

    def send_message(self, to: list[str], subject: str, body: str, thread_id: str = "",
                     cc: list[str] | None = None) -> dict:
        message = self._compose(to, subject, body, cc)
        context = ssl.create_default_context()
        if self.smtp_port == 465:
            server = smtplib.SMTP_SSL(self.smtp_host, 465, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.starttls(context=context)
        with server:
            server.login(self.address, self.password)
            server.send_message(message)
        record = {"message_id": str(message.get("Message-ID") or f"sent-{len(self.sent_by_gateway) + 1}"),
                  "thread_id": thread_id or None, "to": to, "cc": cc or [], "subject": subject,
                  "body": body}
        self.sent_by_gateway.append(record)
        return {"message_id": record["message_id"], "status": "sent", "to": to, "delivery": "real"}

    def list_drafts(self) -> dict:
        return {"drafts": self.saved_drafts}

    def list_sent(self) -> dict:
        return {"sent": self.sent_by_gateway}

    def trash_thread(self, thread_id: str) -> dict:
        return {"error": "not_supported", "detail": "This provider never deletes real mail."}
