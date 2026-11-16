"""Chapter 14: System One, a second model that decides.

Three labs, each against the practice inbox or a request the learner types.
Every lab shows the rule-based answer beside System One's, so the two can be
compared on the same data. With System One off, each lab says so and shows the
rule-based answer alone.
"""
import asyncio
import time

import policy
from fastapi import APIRouter, Depends, HTTPException

from backend.core import calendar_intel, inbox, skills, system_one, tools
from backend.routers.deps import ready
from backend.schemas import QueryReq

router = APIRouter(prefix="/api/system_one", tags=["system_one"], dependencies=[Depends(ready)])

OFF = "System One is off. Set TYPESAFE_API_KEY and start the appbook again to compare the two."


@router.get("/status")
async def status():
    return {"chapter": "System One", **system_one.status(), "costs": system_one.costs(),
            "decisions_made_for": [
                {"decision": "Is this email an attack?", "question": "noul, one for each message",
                 "used_by": "Inbox triage: a second detector beside the tripwire", "in_the_loop": True},
                {"decision": "Which evidence is worth reading?", "question": "choice, with a none option",
                 "used_by": "Meeting preparation: which earlier threads to read", "in_the_loop": True},
                {"decision": "Which procedure applies?", "question": "choice over the skills, and none",
                 "used_by": "Measured in the lab below", "in_the_loop": False},
                {"decision": "Which tools does the request need?", "question": "noul, one for each tool",
                 "used_by": "Measured in the lab below", "in_the_loop": False}],
            "why_tools_stay_bound": "The assistant offers every tool on every turn. A tool list that "
                                    "never changes keeps the prompt prefix stable, so the prefix is "
                                    "cached and earlier reasoning stays valid. The notebook shows the "
                                    "other choice: binding only the tools System One picks."}


@router.get("/decisions")
async def decisions(limit: int = 50):
    return {"decisions": system_one.decisions(min(max(limit, 1), 200)), "costs": system_one.costs(),
            "table": "ppa_decision_log"}


@router.post("/attack_lab")
async def attack_lab():
    """The tripwire and System One, on the same inbox."""
    mails = await inbox.threads()
    started = time.perf_counter()
    await asyncio.to_thread(system_one.screen, mails)
    seconds = round(time.perf_counter() - started, 2)
    rows = []
    for mail in mails:
        patterns = policy.detect_injection(mail["subject"] + "\n" + mail.get("body", ""))
        odds = system_one.probability(mail)
        rows.append({"thread_id": mail["thread_id"], "from_email": mail["from_email"],
                     "tripwire": bool(patterns), "patterns": patterns, "attack_probability": odds,
                     "system_one": odds is not None and odds >= system_one.ATTACK_THRESHOLD})
    rows.sort(key=lambda row: -(row["attack_probability"] or 0))
    return {"threads": len(rows), "seconds": seconds, "threshold": system_one.ATTACK_THRESHOLD,
            "flagged_by_tripwire": sum(row["tripwire"] for row in rows),
            "flagged_by_system_one": sum(row["system_one"] for row in rows),
            "flagged_by_either": sum(row["tripwire"] or row["system_one"] for row in rows),
            "rows": rows, "note": None if system_one.available() else OFF,
            "rule": "A flagged message from a sender the owner has never written to is quarantined. "
                    "A flagged message from a known person is marked and stays where it was."}


@router.post("/select_lab")
async def select_lab(req: QueryReq):
    """Which procedure and which tools a request needs: keyword overlap beside System One."""
    catalogue = {item["name"]: item["description"] for item in tools.catalogue() if item["model_facing"]}
    manifests = {item["name"]: item["description"] for item in skills.manifests()}
    ranked = skills.rank(req.query)
    started = time.perf_counter()
    chosen = await asyncio.to_thread(system_one.select, req.query, manifests, catalogue)
    return {"request": req.query,
            "by_rule": {"skill": ranked[0]["name"] if ranked else None, "tools_offered": len(catalogue),
                        "method": "keyword overlap with each skill's triggers; every tool offered"},
            "by_system_one": None if chosen is None else {
                **chosen, "seconds": round(time.perf_counter() - started, 2),
                "tools_offered": len(chosen["tools"])},
            "note": None if chosen is not None else OFF}


@router.post("/rerank_lab")
async def rerank_lab(req: QueryReq):
    """Which earlier threads are worth reading before one meeting."""
    found = await calendar_intel.meeting_prep(req.query)
    if found is None:
        raise HTTPException(404, "No such event")
    return {"event": {key: found["event"].get(key) for key in ("event_id", "title", "start", "source")},
            "kept": [{"thread_id": item["thread_id"], "subject": item.get("subject")}
                     for item in found.get("earlier_threads", [])],
            "chosen_by": found.get("evidence_chosen_by"), "note": None if system_one.available() else OFF}
