"""Chapter 2: connections, the practice workspace and safe mode.

Nothing here needs an account. The practice workspace is the default, and
connecting a real account is optional. When one is connected, credentials pass
through to the gateway and nowhere else: the harness does not keep, log or
return them, and the gateway stores them in a local file that only the owner
can read.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from backend.core import llm_client, runtime, tracing, websearch
from backend.core.workspace import SYSTEMS, WorkspaceError, workspace
from backend.routers.deps import ready
from backend.schemas import ConnectReq, SwitchReq, SystemReq

router = APIRouter(prefix="/api/connections", tags=["connections"], dependencies=[Depends(ready)])

READ_PROBES = {"mail": ("mail_search_threads", {"label": "INBOX", "max_results": 1}, "threads"),
               "calendar": ("calendar_list_events", None, "events"),
               "notes": ("notes_search", {"query": ""}, "pages")}
NO_SIGN_IN = {
    "title": "Nothing here needs an account",
    "text": "Every chapter and the whole assistant run on the practice workspace. It is the default, "
            "it needs no sign-in, and nothing it does reaches another person.",
    "optional": "Connecting your own mail, calendar or notes is optional and no chapter "
                "depends on it. A provider can refuse or delay it: Google asks an application to pass OAuth "
                "verification, and an administrator can switch app passwords off. If a connection "
                "fails, nothing is stored and the practice workspace stays in use.",
}
DISCLOSURE = [
    {"title": "What is read", "text": "Recent mail threads, calendar events and the notes pages you "
                                     "share. They are read on demand and never copied into the harness "
                                     "database."},
    {"title": "What can be written", "text": "Drafts and private pages are written without asking, "
                                            "because nobody else sees them. Sending mail, creating or "
                                            "answering invitations and editing a shared page each "
                                            "need your approval, one action at a time."},
    {"title": "Where credentials stay", "text": "In one file on this machine that only your user "
                                                "account can read. They are not written to the "
                                                "repository, not returned by any endpoint and not "
                                                "kept in the browser."},
    {"title": "Safe mode", "text": "On by default. With a real account, an approved message to anyone "
                                   "but you is held as a draft, and an approved event is created "
                                   "without other attendees. Switch it off only when you are ready "
                                   "for approved actions to reach other people."},
]


def leaving() -> dict[str, str]:
    """What leaves this machine, as the process is configured now."""
    responder, traced = llm_client.status(), tracing.status()
    parts = ["Claude is the responder: the text the assistant reads, including mail it opens, is sent "
             "to Anthropic to produce an answer." if responder["responder"] == "claude" else
             "The scripted responder answers, so no text is sent to any model."]
    parts.append("A web search sends its search words to Tavily." if websearch.configured() else
                 "Web search is not configured, so no search leaves this machine.")
    parts.append("Tracing is on: every graph step, model call and tool result, mail text included, is "
                 "sent to LangSmith. Set LANGSMITH_TRACING=false before you connect a real mailbox if "
                 "you do not want that." if traced["active"] else
                 "Tracing to LangSmith is off.")
    return {"title": "What leaves this machine", "text": " ".join(parts)}


@router.get("/status")
async def status():
    try:
        providers = await workspace.providers()
    except WorkspaceError as exc:
        providers = {"error": str(exc)}
    return {"chapter": "Connections", **await runtime.connection_status(), "providers": providers,
            "no_sign_in": NO_SIGN_IN, "disclosure": [*DISCLOSURE[:3], leaving(), *DISCLOSURE[3:]],
            "responder": llm_client.status(), "tracing": tracing.status(), "gateway": workspace.status()}


@router.post("/connect")
async def connect(req: ConnectReq):
    """Test the connection through the gateway. Settings are stored only when it works."""
    try:
        result = await workspace.connect(req.system, req.provider, req.settings)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await runtime.rebind()
    return {"connected": result, **await runtime.connection_status()}


@router.post("/disconnect")
async def disconnect(req: SystemReq):
    result = await workspace.disconnect(req.system)
    await runtime.rebind()
    return {"disconnected": result, **await runtime.connection_status()}


@router.post("/test")
async def test(req: SystemReq):
    """Prove the system answers: one small read through its MCP server."""
    import time

    from backend.core import clock

    tool, arguments, key = READ_PROBES[req.system]
    arguments = arguments or {"start_date": clock.today().isoformat()}
    workspace.forget_reads()
    started = time.perf_counter()
    try:
        found = await workspace.call(tool, arguments)
    except WorkspaceError as exc:
        return {"system": req.system, "ok": False, "detail": str(exc)}
    elapsed = round((time.perf_counter() - started) * 1000)
    if found.get("error"):
        return {"system": req.system, "ok": False, "detail": found.get("detail") or found["error"]}
    return {"system": req.system, "ok": True, "tool": tool, "ms": elapsed,
            "detail": f"{len(found.get(key, []))} {key} returned in {elapsed} ms"}


@router.post("/safe_mode")
async def safe_mode(req: SwitchReq):
    await workspace.set_safe_mode(req.enabled)
    return await runtime.connection_status()


@router.get("/overlay.ics")
async def overlay():
    """Blocks the assistant created, as a calendar file the owner can import."""
    return Response(await workspace.overlay(), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="ppa-blocks.ics"'})


assert set(READ_PROBES) == set(SYSTEMS)
