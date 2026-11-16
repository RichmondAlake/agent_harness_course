"""The workspace gateway: mail, calendar and notes over real MCP.

Three Model Context Protocol servers run in one process over streamable HTTP,
the same transport a hosted server uses:

    http://127.0.0.1:8931/mail/mcp
    http://127.0.0.1:8931/calendar/mcp
    http://127.0.0.1:8931/notes/mcp

Behind them sits either the practice workspace (a real public mailbox) or the
owner's own accounts. The harness cannot tell the difference, which is the
point: MCP is the transport, the provider is a deployment choice.

Like hosted servers, these expose more than an assistant should use (trash,
delete, share). The harness allowlist decides what is reachable.

The ``/admin`` routes are plain HTTP, not MCP tools, so a model can never call
them. They require the bearer token.

    PPA_MCP_TOKEN=local-token python workspace_mcp_server.py --port 8931
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "workspace"))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, PlainTextResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from calendars import overlay_ics  # noqa: E402
from gateway import PROVIDERS, Workspace  # noqa: E402

TOKEN = os.environ.get("PPA_MCP_TOKEN", "")
WORKSPACE = Workspace()


def guarded(call, *args: Any, **kwargs: Any) -> dict:
    """Run a provider call and turn a failure into a result the model can read."""
    try:
        return call(*args, **kwargs)
    except Exception as exc:
        return {"error": "provider_failed", "error_type": type(exc).__name__,
                "detail": str(exc)[:300]}


# ── Mail ─────────────────────────────────────────────────────────────────────

mail = FastMCP("ppa-mail", stateless_http=True, json_response=True)


@mail.tool()
def mail_search_threads(query: str = "", label: str = "INBOX", max_results: int = 25) -> dict:
    """List email threads, newest first. Label INBOX is recent mail, SENT is mail the
    owner sent, ALL searches the whole history."""
    return guarded(WORKSPACE.provider("mail").search_threads, query, label, max_results)


@mail.tool()
def mail_get_thread(thread_id: str) -> dict:
    """Read one email thread in full, with every participant."""
    return guarded(WORKSPACE.provider("mail").get_thread, thread_id)


@mail.tool()
def mail_create_draft(to: list[str], subject: str, body: str, thread_id: str = "") -> dict:
    """Save a message as a draft. Nothing is sent and nobody is notified."""
    return guarded(WORKSPACE.provider("mail").create_draft, to, subject, body, thread_id)


@mail.tool()
def mail_send_message(to: list[str], subject: str, body: str, thread_id: str = "",
                      cc: list[str] | None = None) -> dict:
    """Send an email to other people. This cannot be undone."""
    return guarded(WORKSPACE.send_message, to, subject, body, thread_id, cc)


@mail.tool()
def mail_list_drafts() -> dict:
    """List drafts saved through this workspace."""
    return guarded(WORKSPACE.provider("mail").list_drafts)


@mail.tool()
def mail_list_sent() -> dict:
    """List messages sent through this workspace."""
    return guarded(WORKSPACE.provider("mail").list_sent)


@mail.tool()
def mail_trash_thread(thread_id: str) -> dict:
    """Move a thread to the bin."""
    return guarded(WORKSPACE.provider("mail").trash_thread, thread_id)


# ── Calendar ─────────────────────────────────────────────────────────────────

calendar = FastMCP("ppa-calendar", stateless_http=True, json_response=True)


@calendar.tool()
def calendar_list_events(start_date: str, end_date: str = "") -> dict:
    """List calendar events between two ISO dates, inclusive."""
    return guarded(WORKSPACE.provider("calendar").list_events, start_date, end_date)


@calendar.tool()
def calendar_create_event(title: str, start: str, end: str, attendees: list[str] | None = None,
                          description: str = "", kind: str = "focus") -> dict:
    """Create a calendar event. Attendees receive an invitation."""
    return guarded(WORKSPACE.create_event, title, start, end, attendees, description, kind)


@calendar.tool()
def calendar_respond_to_event(event_id: str, response: str, comment: str = "") -> dict:
    """Accept, decline or tentatively accept an invitation. The organiser is notified."""
    return guarded(WORKSPACE.respond_to_event, event_id, response, comment)


@calendar.tool()
def calendar_delete_event(event_id: str) -> dict:
    """Delete a calendar event for every attendee."""
    return guarded(WORKSPACE.provider("calendar").delete_event, event_id)


# ── Notes ────────────────────────────────────────────────────────────────────

notes = FastMCP("ppa-notes", stateless_http=True, json_response=True)


@notes.tool()
def notes_search(query: str = "") -> dict:
    """Find pages by title or content."""
    return guarded(WORKSPACE.provider("notes").search_pages, query)


@notes.tool()
def notes_get_page(page_id: str) -> dict:
    """Read one page, including whether other people can see it."""
    return guarded(WORKSPACE.provider("notes").get_page, page_id)


@notes.tool()
def notes_create_page(title: str, body: str) -> dict:
    """Create a private page that only the owner can see."""
    return guarded(WORKSPACE.provider("notes").create_page, title, body)


@notes.tool()
def notes_append_to_page(page_id: str, text: str) -> dict:
    """Append text to a page. On a shared page, other people see the change."""
    return guarded(WORKSPACE.append_to_page, page_id, text)


@notes.tool()
def notes_share_page(page_id: str, email: str) -> dict:
    """Share a page with another person."""
    return guarded(WORKSPACE.provider("notes").share_page, page_id, email)


@notes.tool()
def notes_delete_page(page_id: str) -> dict:
    """Permanently delete a page."""
    return guarded(WORKSPACE.provider("notes").delete_page, page_id)


# ── Admin HTTP API ───────────────────────────────────────────────────────────

SERVERS = {"mail": mail, "calendar": calendar, "notes": notes}


def authorised(request: Request) -> bool:
    return not TOKEN or request.headers.get("authorization") == f"Bearer {TOKEN}"


def admin(handler):
    async def route(request: Request) -> JSONResponse:
        if not authorised(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json() if request.method == "POST" and await request.body() else {}
            return JSONResponse(handler(body))
        except Exception as exc:
            return JSONResponse({"error": str(exc)[:300], "error_type": type(exc).__name__},
                                status_code=400)
    return route


async def health(_: Request) -> JSONResponse:
    return JSONResponse({**WORKSPACE.status(), "auth_required": bool(TOKEN)})


async def overlay(request: Request) -> PlainTextResponse:
    if not authorised(request):
        return PlainTextResponse("unauthorized", status_code=401)
    provider = WORKSPACE.provider("calendar")
    events = getattr(provider, "overlay", None) or getattr(provider, "created", [])
    return PlainTextResponse(overlay_ics(events), media_type="text/calendar")


def set_clock(body: dict) -> dict:
    if not WORKSPACE.practising:
        raise ValueError("The clock can be pinned only in the practice workspace")
    return {"clock": WORKSPACE.practice.set_clock(body.get("now")).isoformat(timespec="minutes")}


def reset(_: dict) -> dict:
    WORKSPACE.practice.reset()
    WORKSPACE.effects.clear()
    WORKSPACE.keep_effects()
    return {"status": "reset", "clock": WORKSPACE.now().isoformat(timespec="minutes")}


def set_safe_mode(body: dict) -> dict:
    WORKSPACE.safe_mode = bool(body.get("enabled", True))
    return {"safe_mode": WORKSPACE.safe_mode}


def practice_inbox(_: dict) -> dict:
    """The inbox in full, for trusted harness code that applies governed triage."""
    return {"emails": WORKSPACE.provider("mail").inbox()}


ADMIN = {
    "/admin/providers": (lambda _: PROVIDERS, ["GET"]),
    "/admin/world": (lambda _: WORKSPACE.world(), ["GET"]),
    "/admin/effects": (lambda _: {"effects": WORKSPACE.effects}, ["GET"]),
    "/admin/inbox": (practice_inbox, ["GET"]),
    "/admin/connect": (lambda body: WORKSPACE.connect(
        body["system"], body["provider"], body.get("settings", {})), ["POST"]),
    "/admin/disconnect": (lambda body: WORKSPACE.disconnect(body["system"]), ["POST"]),
    "/admin/safe_mode": (set_safe_mode, ["POST"]),
    "/admin/clock": (set_clock, ["POST"]),
    "/admin/reset": (reset, ["POST"]),
}


class BearerAuth:
    """Reject MCP traffic that lacks the shared bearer token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and TOKEN and scope["path"].rstrip("/").endswith("/mcp"):
            headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
            if headers.get("authorization") != f"Bearer {TOKEN}":
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(_: Starlette):
    async with contextlib.AsyncExitStack() as stack:
        for server in SERVERS.values():
            await stack.enter_async_context(server.session_manager.run())
        yield


def build_app() -> Any:
    routes = [Route("/health", health), Route("/admin/overlay.ics", overlay)]
    routes += [Route(path, admin(handler), methods=methods)
               for path, (handler, methods) in ADMIN.items()]
    routes += [Mount(f"/{name}", app=server.streamable_http_app())
               for name, server in SERVERS.items()]
    return BearerAuth(Starlette(routes=routes, lifespan=lifespan))


app = build_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="PPA workspace gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PPA_MCP_PORT", "8931")))
    parser.add_argument("--describe", action="store_true", help="Print the tool catalogue and exit.")
    args = parser.parse_args()
    if args.describe:
        import asyncio

        print(json.dumps({name: [tool.name for tool in asyncio.run(server.list_tools())]
                          for name, server in SERVERS.items()}, indent=2))
        return
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
