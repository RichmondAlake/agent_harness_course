"""Chapter 15: the context and cost ledger."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import ledger, llm_client, trajectories
from backend.routers.deps import ready

router = APIRouter(prefix="/api/context_cost", tags=["context_cost"], dependencies=[Depends(ready)])


@router.get("/status")
async def status(limit: int = 40):
    """Every figure the chapter draws: layers per turn, cost per turn, running cost, what caching saved."""
    model = llm_client.status()
    return {"chapter": "Context and cost", **ledger.summary(min(max(limit, 1), 200)),
            "responder": model["label"], "model_called": model["responder"] == "claude",
            "caching": {"on": True, "breakpoints": [
                "the last block of the system prompt: the tool list and the system prompt are cached together",
                "a top-level breakpoint on every call: the conversation so far is cached"],
                "rule": "The system prompt and the tool list never change inside a conversation, and "
                        "messages are only ever added. A cache entry is found again only when the text "
                        "before it is the same, byte for byte."},
            "tables": ["ppa_model_calls", "ppa_turns"]}


@router.get("/turn/{turn_id}")
async def turn(turn_id: str):
    """The model calls of one turn, with its layers and its totals."""
    found = trajectories.get(turn_id)
    if found is None:
        raise HTTPException(404, "No such turn")
    return {"turn": found, "calls": ledger.calls(turn_id), "totals": ledger.turn_total(turn_id),
            "prices": ledger.prices()}
