"""The practice workspace as three MCP servers, for the done-for-you track.

MemoRizz speaks version 2 of the MCP Python SDK. This file serves the shared
practice workspace (``part_3/_shared``) through that version, over streamable
HTTP, on one local port:

    http://127.0.0.1:8941/mail/mcp
    http://127.0.0.1:8941/calendar/mcp
    http://127.0.0.1:8941/notes/mcp

Like a hosted server, it offers more than an assistant should use (send,
trash, delete, share). The allowlist in the harness decides what is reachable.

    python workspace_gateway.py --port 8941

Environment: ``PPA_PRACTICE_NOW`` pins the clock, ``PPA_PRACTICE_STATE`` names
the file that keeps drafts, events and pages between restarts, and
``PPA_GENERATED_CALENDAR=1`` fills the week with working sessions.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Any, Callable

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED / "workspace"))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from gateway import Workspace  # noqa: E402

# server -> tool name -> (method on the workspace or its provider, description)
TOOLS: dict[str, dict[str, str]] = {
    "mail": {
        "mail_search_threads": "List email threads, newest first. Label INBOX is recent mail, "
                               "SENT is mail the owner sent, ALL searches the whole history.",
        "mail_get_thread": "Read one email thread in full, with every participant.",
        "mail_create_draft": "Save a message as a draft. Nothing is sent and nobody is notified.",
        "mail_send_message": "Send an email to other people. This cannot be undone.",
        "mail_list_drafts": "List drafts saved through this workspace.",
        "mail_list_sent": "List messages sent through this workspace.",
        "mail_trash_thread": "Move a thread to the bin.",
    },
    "calendar": {
        "calendar_list_events": "List calendar events between two ISO dates, inclusive.",
        "calendar_create_event": "Create a calendar event. Attendees receive an invitation.",
        "calendar_respond_to_event": "Accept, decline or tentatively accept an invitation. "
                                     "The organiser is notified.",
        "calendar_delete_event": "Delete a calendar event for every attendee.",
    },
    "notes": {
        "notes_search": "Find pages by title or content.",
        "notes_get_page": "Read one page, including whether other people can see it.",
        "notes_create_page": "Create a private page that only the owner can see.",
        "notes_append_to_page": "Append text to a page. On a shared page, other people see the change.",
        "notes_share_page": "Share a page with another person.",
        "notes_delete_page": "Permanently delete a page.",
    },
}


def build_servers(workspace: Workspace) -> dict[str, MCPServer]:
    """One MCP server per system of record, each tool a thin call into the workspace."""
    mail, calendar, notes = (MCPServer(f"ppa-{name}") for name in TOOLS)

    def provider(system: str) -> Any:
        return workspace.provider(system)

    def guarded(call: Callable[..., dict], *args: Any) -> dict:
        """Turn a provider failure into a result the model can read."""
        try:
            return call(*args)
        except Exception as exc:
            return {"error": "provider_failed", "error_type": type(exc).__name__, "detail": str(exc)[:300]}

    def describe(server: MCPServer, system: str):
        return lambda function: server.tool(description=TOOLS[system][function.__name__])(function)

    @describe(mail, "mail")
    def mail_search_threads(query: str = "", label: str = "INBOX", max_results: int = 25) -> dict:
        return guarded(provider("mail").search_threads, query, label, max_results)

    @describe(mail, "mail")
    def mail_get_thread(thread_id: str) -> dict:
        return guarded(provider("mail").get_thread, thread_id)

    @describe(mail, "mail")
    def mail_create_draft(to: list[str], subject: str, body: str, thread_id: str = "") -> dict:
        return guarded(provider("mail").create_draft, to, subject, body, thread_id)

    @describe(mail, "mail")
    def mail_send_message(to: list[str], subject: str, body: str, thread_id: str = "") -> dict:
        return guarded(workspace.send_message, to, subject, body, thread_id, None)

    @describe(mail, "mail")
    def mail_list_drafts() -> dict:
        return guarded(provider("mail").list_drafts)

    @describe(mail, "mail")
    def mail_list_sent() -> dict:
        return guarded(provider("mail").list_sent)

    @describe(mail, "mail")
    def mail_trash_thread(thread_id: str) -> dict:
        return guarded(provider("mail").trash_thread, thread_id)

    @describe(calendar, "calendar")
    def calendar_list_events(start_date: str, end_date: str = "") -> dict:
        return guarded(provider("calendar").list_events, start_date, end_date)

    @describe(calendar, "calendar")
    def calendar_create_event(title: str, start: str, end: str, description: str = "",
                              kind: str = "focus") -> dict:
        return guarded(workspace.create_event, title, start, end, None, description, kind)

    @describe(calendar, "calendar")
    def calendar_respond_to_event(event_id: str, response: str, comment: str = "") -> dict:
        return guarded(workspace.respond_to_event, event_id, response, comment)

    @describe(calendar, "calendar")
    def calendar_delete_event(event_id: str) -> dict:
        return guarded(provider("calendar").delete_event, event_id)

    @describe(notes, "notes")
    def notes_search(query: str = "") -> dict:
        return guarded(provider("notes").search_pages, query)

    @describe(notes, "notes")
    def notes_get_page(page_id: str) -> dict:
        return guarded(provider("notes").get_page, page_id)

    @describe(notes, "notes")
    def notes_create_page(title: str, body: str) -> dict:
        return guarded(provider("notes").create_page, title, body)

    @describe(notes, "notes")
    def notes_append_to_page(page_id: str, text: str) -> dict:
        return guarded(workspace.append_to_page, page_id, text)

    @describe(notes, "notes")
    def notes_share_page(page_id: str, email: str) -> dict:
        return guarded(provider("notes").share_page, page_id, email)

    @describe(notes, "notes")
    def notes_delete_page(page_id: str) -> dict:
        return guarded(provider("notes").delete_page, page_id)

    return {"mail": mail, "calendar": calendar, "notes": notes}


def build_app(workspace: Workspace | None = None) -> Starlette:
    workspace = workspace or Workspace()
    servers = build_servers(workspace)
    apps = {name: server.streamable_http_app(stateless_http=True, json_response=True)
            for name, server in servers.items()}

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        async with contextlib.AsyncExitStack() as stack:
            for server in servers.values():
                await stack.enter_async_context(server.session_manager.run())
            yield

    async def health(_) -> JSONResponse:
        return JSONResponse(workspace.status())

    routes = [Route("/health", health)] + [Mount(f"/{name}", app=app) for name, app in apps.items()]
    return Starlette(routes=routes, lifespan=lifespan)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="PPA practice workspace over MCP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8941)
    args = parser.parse_args()
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
