"""Derive contacts and VIPs from the mail the owner actually sends.

Nobody maintains a VIP list by hand. The people who matter are the people
you write to. This module turns that observation into a governed definition:

    A contact is anyone the owner has written to in the trailing window.
    A VIP is one of the ``top_k`` contacts by messages sent, provided the
    owner wrote to them at least ``min_messages`` times.

The rule is inspectable and the same for a practice mailbox and a real one.
An explicit user statement ("treat Dana as a VIP") overrides it in memory.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from textutil import display_name, domain_of

WINDOW_DAYS = 90
TOP_K = 5
MIN_MESSAGES = 3
MAX_DIRECT_RECIPIENTS = 6   # a message to many people says little about any one of them


def derive_contacts(sent: list[dict[str, Any]], owner_email: str, now: datetime,
                    window_days: int = WINDOW_DAYS, top_k: int = TOP_K,
                    min_messages: int = MIN_MESSAGES) -> list[dict[str, Any]]:
    """Return contacts with a derived ``is_vip`` flag, most written-to first."""
    low = (now - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    high = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    counts: Counter[str] = Counter()
    last_written: dict[str, str] = {}
    for message in sent:
        if not low <= message["stamp"] <= high:
            continue
        recipients = [item for item in message["recipients"] if item != owner_email]
        if not recipients or len(recipients) > MAX_DIRECT_RECIPIENTS:
            continue
        for address in recipients:
            counts[address] += 1
            last_written[address] = max(last_written.get(address, ""), message["stamp"])
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    vips = {address for address, total in ranked[:top_k] if total >= min_messages}
    own_domain = domain_of(owner_email)
    return [{
        "contact_id": "C-" + address.split("@", 1)[0].upper().replace(".", "-")[:24],
        "name": display_name(address), "email": address,
        "organisation": domain_of(address),
        "relationship": "colleague" if domain_of(address) == own_domain else "external",
        "role": "", "is_vip": address in vips, "vip_source": "derived" if address in vips else "",
        "messages_sent": total, "last_written_at": last_written[address],
    } for address, total in ranked]
