"""Small, dependency-free text helpers shared by every workspace provider."""
from __future__ import annotations

import hashlib
import html
import re

SUBJECT_PREFIX = re.compile(
    r"^\s*((re|fw|fwd|updated|canceled|cancelled|accepted|declined|tentative)\s*:\s*)+", re.I)
QUOTE_MARKERS = (
    re.compile(r"^-{2,}\s*original message\s*-{2,}", re.I | re.M),
    re.compile(r"^-{2,}\s*forwarded by .*", re.I | re.M),
    re.compile(r"^on .{10,80} wrote:\s*$", re.I | re.M),
    re.compile(r"^from:\s.+\n(sent|date):\s", re.I | re.M),
)


def normalise_subject(subject: str) -> str:
    """Strip reply, forward and calendar prefixes so a thread has one subject."""
    return re.sub(r"\s+", " ", SUBJECT_PREFIX.sub("", subject or "")).strip().lower()


def thread_id_for(subject: str, fallback: str) -> str:
    """A stable thread identifier derived from the normalised subject."""
    key = normalise_subject(subject) or fallback
    return "thr-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def short_id(prefix: str, value: str) -> str:
    return f"{prefix}-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def new_text(body: str) -> str:
    """Return what the sender wrote, without the quoted history below it."""
    cut = len(body)
    for marker in QUOTE_MARKERS:
        match = marker.search(body)
        if match:
            cut = min(cut, match.start())
    lines = [line for line in body[:cut].splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def snippet(body: str, length: int = 160) -> str:
    return re.sub(r"\s+", " ", new_text(body) or body).strip()[:length]


def display_name(address: str) -> str:
    """Derive a readable name from an address: ``jane.q.doe@x`` becomes ``Jane Q Doe``."""
    local = address.split("@", 1)[0]
    parts = [part for part in re.split(r"[._\-]+", local) if part]
    return " ".join(part.capitalize() for part in parts) or address


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def html_to_text(markup: str) -> str:
    """Reduce an HTML email body to readable text."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", markup)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def clip(text: str, limit: int = 12000) -> str:
    """Bound a body so one long email cannot flood the model's context."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} more characters not shown]"
