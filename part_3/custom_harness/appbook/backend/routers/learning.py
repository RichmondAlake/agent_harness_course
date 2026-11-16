"""Chapter 16: trajectories, and learning from them."""
import asyncio
import difflib

from fastapi import APIRouter, Depends, HTTPException

from backend.config import settings
from backend.core import learning, skills, system_one, trajectories
from backend.core.agent import ThreadBusy
from backend.routers.deps import ready
from backend.schemas import ActivateReq, CorrectionApplyReq, CorrectionReq, DraftSkillReq, ReasonReq, RefineReq

router = APIRouter(prefix="/api/learning", tags=["learning"], dependencies=[Depends(ready)])


def _version(name: str, number: int) -> dict:
    found = skills.version(name, number)
    if found is None:
        raise HTTPException(404, "No such skill version")
    return found


@router.get("/status")
async def status(limit: int = 60):
    return {"chapter": "Learning from its own traces",
            "trajectories": trajectories.recent(min(max(limit, 1), 200)), "counts": trajectories.counts(),
            "candidates": learning.repeated_workflows(), "skills": learning.catalogue(),
            "log": skills.log(60), "corrections": learning.lessons(),
            "gate": [{"id": key, "name": title, "explains": about} for key, title, about in learning.CHECKS],
            "frozen": list(learning.FROZEN), "destinations": learning.DESTINATIONS,
            "helper_tools": sorted(learning.HELPER_TOOLS), "minimum_repeats": learning.MINIMUM_REPEATS,
            "written_by": "Claude writes the candidate" if settings.claude_available
            else "A template writes the candidate: no model is available",
            "routed_by": "System One routes a correction" if system_one.available()
            else "A written rule routes a correction: System One is off",
            "tables": ["ppa_turns", "ppa_skill_versions", "ppa_skill_registry", "ppa_skill_log"]}


@router.get("/trajectories/{turn_id}")
async def trajectory(turn_id: str):
    found = trajectories.detail(turn_id)
    if found is None:
        raise HTTPException(404, "No such turn")
    return found


@router.post("/sample_week")
async def sample_week():
    """Scripted practice data: five turns, so that the chapter has something to learn from."""
    try:
        return await learning.load_sample_week()
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/draft")
async def draft(req: DraftSkillReq):
    """Write a candidate skill from turns that share one workflow. It is stored, and not live."""
    try:
        return await learning.draft_skill(req.turn_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/skills/{name}/{version}/gate")
async def gate(name: str, version: int):
    """Run the five checks. Each one is also published on the event stream as it finishes."""
    _version(name, version)
    return await learning.gate_skill(name, version)


@router.post("/skills/{name}/{version}/promote")
async def promote(name: str, version: int):
    _version(name, version)
    try:
        return learning.promote(name, version)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/skills/{name}/activate")
async def activate(name: str, req: ActivateReq):
    """Move the live pointer to any stored version. This is how a roll back is done."""
    _version(name, req.version)
    return learning.activate(name, req.version, req.reason)


@router.post("/skills/{name}/retire")
async def retire(name: str, req: ReasonReq):
    if not learning.retire(name, req.reason):
        raise HTTPException(404, "That skill is not live")
    return {"name": name, "live": False}


@router.post("/skills/{name}/refine")
async def refine(name: str, req: RefineReq):
    """Write the next version of a live skill with a correction in it. It is a candidate until it passes."""
    try:
        return await learning.refine_skill(name, req.correction, turn_id=req.turn_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/skills/{name}/diff")
async def diff(name: str, a: int, b: int):
    """What changed between two stored versions of a procedure."""
    before, after = _version(name, a), _version(name, b)
    lines = []
    for line in difflib.unified_diff(before["body"].splitlines(), after["body"].splitlines(),
                                     f"version {a}", f"version {b}", lineterm="", n=50):
        kind = ("meta" if line.startswith(("---", "+++", "@@")) else
                "added" if line.startswith("+") else "removed" if line.startswith("-") else "same")
        lines.append({"kind": kind, "text": line if kind == "meta" else line[1:]})
    return {"name": name, "a": a, "b": b, "lines": lines, "identical": not lines,
            "description_changed": before["description"] != after["description"]}


@router.post("/correction/route")
async def route(req: CorrectionReq):
    """Decide where a correction belongs. Nothing is changed by this call."""
    try:
        return await asyncio.to_thread(learning.route_lesson, req.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/correction/apply")
async def apply(req: CorrectionApplyReq):
    """Carry a routed correction to its destination: the skill, long-term memory, or nowhere."""
    try:
        return await learning.apply_lesson(req.text, req.destination, skill=req.skill, turn_id=req.turn_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
