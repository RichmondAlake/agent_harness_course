"""Chapter 13: the weekly review."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import clock, review
from backend.core.agent import ThreadBusy, agent
from backend.routers.deps import ready

router = APIRouter(prefix="/api/weekly_review", tags=["weekly_review"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    return {"chapter": "Weekly review", "clock": clock.status(), "review": review.weekly(),
            "note": "Computed from what the harness recorded. Nothing is seeded, so an unused "
                    "workspace shows an empty review."}


@router.post("/run")
async def run():
    """The same review as a request to the assistant, through the loop."""
    try:
        outcome = await agent.run("Run my weekly review.", trigger="weekly_review")
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return {**outcome, "review": review.weekly()}
