"""Governed meaning: the same question read naively and with a definition.

A naive reading guesses from surface features. A governed reading applies one
written definition from the shared policy. Both run over the same live data,
so the difference shown is the difference the definition makes.
"""
from __future__ import annotations

import re
from typing import Any

import policy

from backend.core import calendar_intel, clock, inbox, store, tasks, world

URGENT_WORDS = ("urgent", "asap", "immediately", "action required", "important", "today", "reminder")
QUESTIONS = {
    "urgent": "What is urgent?",
    "free": "What is free today?",
    "vip": "Who is a VIP?",
    "overbooked": "Is my week over-booked?",
}


def definitions() -> list[dict[str, str]]:
    """The definitions every answer is held to, with the owner's own numbers."""
    persona = world.persona()
    return [
        {"term": "urgent", "definition": "An open task that is overdue, due within 24 hours, or priority 1.",
         "source": "policy.is_urgent"},
        {"term": "free", "definition": f"A gap inside working hours ({persona['work_start']} to "
                                       f"{persona['work_end']}) that no event occupies, that has not "
                                       f"passed, and that can hold one {persona['pomodoro_minutes']}-minute "
                                       "Pomodoro.", "source": "policy.free_slots"},
        {"term": "VIP", "definition": "A contact the harness holds with the VIP flag set. Wording, "
                                      "labels and job titles do not make a VIP.",
         "source": "ppa_contacts.is_vip"},
        {"term": "over-booked", "definition": f"A day with more than {persona['max_meeting_minutes_per_day']} "
                                              "meeting minutes. Each day is judged on its own.",
         "source": "policy.day_load"},
        {"term": "meeting rule", "definition": f"No meeting starts before {persona['no_meetings_before']}.",
         "source": "policy.meeting_rule_violations"},
        {"term": "already tracked", "definition": "A thread whose ID is the source of an open task. "
                                                  "It is cited, never raised twice.",
         "source": "policy.triage_signals"},
        {"term": "quarantine", "definition": "Instruction-like text from a sender the harness does not "
                                             "know. Reported by ID, never opened, answered or forwarded.",
         "source": "policy.detect_injection"},
        {"term": "slipping", "definition": "An open task carried over at least twice.",
         "source": "policy.slipping_tasks"},
        {"term": "stale", "definition": "An open task with no due date, untouched for 30 days. "
                                        "A candidate to drop, not to nag about.",
         "source": "policy.stale_tasks"},
    ]


def _sounds_urgent(text: str) -> list[str]:
    lowered = text.lower()
    return [word for word in URGENT_WORDS if re.search(rf"\b{re.escape(word)}\b", lowered)]


async def _urgent() -> dict[str, Any]:
    triage = await inbox.triage()
    naive = [{"id": row["thread_id"], "label": row["subject"], "why": "wording: " + ", ".join(words),
              "category": row["category"]}
             for row in triage["rows"] if (words := _sounds_urgent(row["subject"] + " " + row["body"]))]
    naive += [{"id": item["task_id"], "label": item["title"], "why": "wording: " + ", ".join(words),
               "category": "task"}
              for item in tasks.governed() if (words := _sounds_urgent(item["title"]))]
    governed = [{"id": item["task_id"], "label": item["title"],
                 "why": "priority 1" if item["priority"] == 1 else f"due {item['due_at']}"}
                for item in tasks.governed() if item["urgent"]]
    waiting = [{"id": row["thread_id"], "label": row["subject"], "why": row["reason"]}
               for row in triage["rows"] if row["category"] in inbox.ACTIONABLE and row["vip"]]
    flaws = [f"{item['id']} sounds urgent but is {item['category']}" for item in naive
             if item["category"] in ("quarantine", "archive", "tracked")]
    return {"naive": {"method": "Anything whose wording sounds urgent: "
                                + ", ".join(URGENT_WORDS) + ".", "answer": naive, "flaws": flaws},
            "governed": {"answer": governed, "also": waiting,
                         "also_label": "Actionable threads from VIP contacts, which triage ranks first"}}


async def _free() -> dict[str, Any]:
    day = clock.today()
    overview = await calendar_intel.overview(day)
    cursor = clock.at(day, "00:00")
    naive = []
    for event in [item for item in overview["events"] if item["kind"] == "meeting"]:
        start, end = policy.parse_dt(event["start"]), policy.parse_dt(event["end"])
        if start > cursor:
            naive.append({"start_local": policy.hhmm(cursor), "end_local": policy.hhmm(start),
                          "minutes": int((start - cursor).total_seconds() // 60)})
        cursor = max(cursor, end)
    naive.append({"start_local": policy.hhmm(cursor), "end_local": "24:00",
                  "minutes": int((clock.at(day, "23:59") - cursor).total_seconds() // 60) + 1})
    hidden = [item for item in overview["events"] if item["kind"] != "meeting"]
    flaws = [f"treats '{item['title']}' ({policy.hhmm(policy.parse_dt(item['start']))}) as free"
             for item in hidden]
    flaws.append("ignores working hours, time that has passed and the minimum slot length")
    return {"naive": {"method": "Every gap between meetings, across the whole day.",
                      "answer": naive, "flaws": flaws},
            "governed": {"answer": overview["free_slots"], "rules": overview["rules"]}}


async def _vip() -> dict[str, Any]:
    triage = await inbox.triage()
    seen: dict[str, dict[str, Any]] = {}
    for row in triage["rows"]:
        reasons = []
        if "IMPORTANT" in row["labels"]:
            reasons.append("mail labelled IMPORTANT")
        if _sounds_urgent(row["subject"]):
            reasons.append("urgent wording in the subject")
        if reasons:
            seen.setdefault(row["from_email"], {
                "id": row["from_email"], "label": row["from_name"], "why": "; ".join(reasons),
                "known_sender": row["trust"] != "unknown", "category": row["category"]})
    governed = [{"id": item["email"], "label": item["name"], "why": item["role"] or item["relationship"]}
                for item in store.contacts() if item["is_vip"]]
    flagged = {item["id"] for item in governed}
    flaws = [f"{item['id']} is not a known contact" for item in seen.values() if not item["known_sender"]]
    flaws += [f"{item['id']} is a VIP the naive reading missed" for item in governed
              if item["id"] not in seen]
    flaws += [f"{item['id']} is not a VIP" for item in seen.values()
              if item["known_sender"] and item["id"] not in flagged]
    return {"naive": {"method": "Whoever sends mail that is labelled important or worded urgently.",
                      "answer": list(seen.values()), "flaws": flaws},
            "governed": {"answer": governed}}


async def _overbooked() -> dict[str, Any]:
    persona = world.persona()
    loads = await calendar_intel.week()
    average = round(sum(item["meeting_minutes"] for item in loads) / len(loads))
    limit = persona["max_meeting_minutes_per_day"]
    verdict = "over-booked" if average > limit else "not over-booked"
    over = [item for item in loads if item["overbooked"]]
    flaws = [f"{item['weekday']} carries {item['meeting_minutes']} meeting minutes, hidden by the average"
             for item in over] if average <= limit else []
    return {"naive": {"method": "Average meeting minutes per day across the week, against the daily limit.",
                      "answer": [{"id": "week", "label": f"{average} minutes a day on average",
                                  "why": f"{verdict} against the {limit}-minute limit"}],
                      "flaws": flaws},
            "governed": {"answer": loads, "overbooked_days": [item["day"] for item in over]}}


async def compare(question: str) -> dict[str, Any]:
    """Answer one question both ways over the same live data."""
    handlers = {"urgent": _urgent, "free": _free, "vip": _vip, "overbooked": _overbooked}
    if question not in handlers:
        raise KeyError(question)
    result = await handlers[question]()
    term = {"vip": "VIP", "overbooked": "over-booked"}.get(question, question)
    result["governed"].update(next(item for item in definitions() if item["term"] == term))
    return {"question": question, "text": QUESTIONS[question], "as_of": clock.stamp(), **result}
