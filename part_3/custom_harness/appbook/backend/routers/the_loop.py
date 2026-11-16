"""Chapter 11: the loop, its trace and its checkpoints."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import llm_client, skills, store, tools
from backend.core.agent import agent, build_context, system_prompt
from backend.core.memory import memory_provider
from backend.core import clock
from backend.routers.deps import ready
from backend.schemas import QueryReq

router = APIRouter(prefix="/api/the_loop", tags=["the_loop"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    definitions = tools.schemas()
    return {"chapter": "The loop", **agent.describe(), "model": llm_client.status(),
            "runs": [{key: item[key] for key in ("run_id", "thread_id", "trigger", "responder", "status",
                                                 "request", "real_started_at")} | {
                "tokens": item["trace"].get("tokens", {}).get("total", 0),
                "latency_ms": item["trace"].get("latency_ms"),
                "model_calls": item["trace"].get("model_calls")} for item in agent.runs(25)],
            "threads": agent.threads(),
            "prefix": {"system_prompt_tokens": skills.estimate_tokens(system_prompt()),
                       "tool_definitions": len(definitions),
                       "tool_definition_tokens": skills.estimate_tokens(store.dumps(definitions)),
                       "method": "estimated at four characters per token"}}


@router.get("/trace/{run_id}")
async def trace(run_id: str):
    found = store.row("SELECT * FROM ppa_agent_runs WHERE run_id=?", (run_id,))
    if found is None:
        raise HTTPException(404, "No such run")
    return {**found, "trace": store.loads(found["trace"], {})}


@router.post("/context")
async def context(req: QueryReq):
    """Show what would be assembled for a request, without calling the model."""
    turn = {"request": req.query, "trigger": "chat", "session_id": clock.session_id(),
            "thread_id": "preview", "run_id": "preview"}
    standing = memory_provider.standing()
    recalled = memory_provider.recall(req.query, limit=6,
                                      memory_types=("fact", "person", "commitment", "episode"))
    volatile = build_context(turn, standing, recalled)
    stable = system_prompt()
    return {"stable_prefix": {"system_prompt": stable, "tokens": skills.estimate_tokens(stable),
                              "tools": [item["name"] for item in tools.schemas()],
                              "rule": "Frozen when a conversation starts and never edited."},
            "first_user_message": f"{volatile}\n\n<request>\n{req.query}\n</request>",
            "volatile_tokens": skills.estimate_tokens(volatile),
            "rule": "Everything that changes between turns travels here, so earlier turns are never rewritten."}
