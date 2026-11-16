"""The only module that talks to the workspace gateway.

The gateway is one local process that serves mail, calendar and notes as three
real MCP servers over streamable HTTP, plus an operator API for connections,
safe mode, the practice clock and evidence. Behind it sits either the practice
workspace or the owner's own accounts; the harness cannot tell the difference.

This adapter launches the gateway, holds the tool-name map and the harness
allowlist, and is the single seam for every read and write. Like any hosted
server, the gateway offers more than an assistant should use. A tool that is
not on the allowlist is never exposed, whatever the server advertises.
"""
from __future__ import annotations

import asyncio
import atexit
import collections
import contextvars
import json
import os
import subprocess
import sys
import time
from typing import Any

import httpx

from backend.config import DATA_DIR, settings
from backend.core import world
from backend.core.events import bus

SYSTEMS = ("mail", "calendar", "notes")

# Harness allowlist: tool name -> effect tier.
ALLOWLIST: dict[str, str] = {
    "mail_search_threads": "automatic", "mail_get_thread": "automatic",
    "mail_list_drafts": "automatic", "mail_list_sent": "automatic",
    "mail_create_draft": "automatic", "mail_send_message": "approval",
    "calendar_list_events": "automatic", "calendar_create_event": "approval",
    "calendar_respond_to_event": "approval",
    "notes_search": "automatic", "notes_get_page": "automatic",
    "notes_create_page": "automatic", "notes_append_to_page": "conditional",
}
READ_TOOLS = frozenset({"mail_search_threads", "mail_get_thread", "mail_list_drafts", "mail_list_sent",
                        "calendar_list_events", "notes_search", "notes_get_page"})
TIER_RULES = {
    "automatic": "Runs without asking. Nobody else can see the result.",
    "approval": "Pauses for a human decision. Another person will see the result.",
    "conditional": "Automatic on a private page, approval on a shared page.",
    "never": "The server offers it. The allowlist does not, so it cannot be reached.",
}
READ_CACHE_SECONDS = 20

# Set by the agent loop so every gateway call lands in the turn's trace.
call_log: contextvars.ContextVar[list | None] = contextvars.ContextVar("ppa_mcp_calls", default=None)
# The last MCP calls with their arguments and results, for the "last turn" strip of the MCP chapter.
# Kept in memory only: mail text is never written to the appbook's store.
MCP_HISTORY: collections.deque = collections.deque(maxlen=200)
current_turn: dict[str, str] = {}


def _remember_call(entry: dict[str, Any], arguments: dict[str, Any], result: Any) -> None:
    preview = json.dumps(result, default=str, indent=1) if result is not None else ""
    MCP_HISTORY.append({**entry, "turn_id": current_turn.get("turn_id"), "request": current_turn.get("request"),
                        "arguments": arguments, "result": preview[:2500], "truncated": len(preview) > 2500,
                        "at": time.strftime("%H:%M:%S")})


def last_turn_calls() -> dict[str, Any]:
    """The MCP calls of the most recent Assistant turn that made any, in order."""
    turns = [item["turn_id"] for item in MCP_HISTORY if item["turn_id"]]
    if not turns:
        return {"turn_id": None, "request": None, "calls": []}
    calls = [item for item in MCP_HISTORY if item["turn_id"] == turns[-1]]
    return {"turn_id": turns[-1], "request": calls[0]["request"], "calls": calls}


class WorkspaceError(RuntimeError):
    """The gateway refused, failed or could not be reached."""


class ToolNotAllowed(WorkspaceError):
    """The tool exists on the server but is not on the harness allowlist."""


def parse_result(result: Any) -> dict[str, Any]:
    """MCP results arrive as ``[{"type": "text", "text": "<json>"}]``."""
    if isinstance(result, tuple):
        result = result[0]
    content = getattr(result, "content", result)
    if isinstance(content, list):
        content = "".join(block.get("text", "") if isinstance(block, dict) else str(block)
                          for block in content)
    if isinstance(content, dict):
        return content
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return {"text": str(content)}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


class Workspace:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.owned = False
        self.ready = False
        self.error: str | None = None
        self.health: dict[str, Any] = {}
        self.provenance: dict[str, Any] | None = None
        self.tools: dict[str, Any] = {}
        self.offered: dict[str, list[dict[str, Any]]] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._client: httpx.AsyncClient | None = None
        atexit.register(self._terminate)

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.mcp_base_url, timeout=httpx.Timeout(15, read=120),
                headers={"Authorization": f"Bearer {settings.mcp_token}"})
        return self._client

    # ── Process ──────────────────────────────────────────────────────────────

    async def probe(self) -> dict[str, Any] | None:
        try:
            response = await self._http.get("/health", timeout=3)
            payload = response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None
        if payload and payload.get("status") == "ok" and "systems" in payload:
            self.health = payload
            return payload
        return None

    async def start(self) -> dict[str, Any]:
        """Reuse a healthy gateway on the port, otherwise launch one and wait for it."""
        self.error = None
        if await self.probe() is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            log = open(DATA_DIR / "gateway.log", "ab")
            env = {key: value for key, value in os.environ.items()
                   if key not in {"ANTHROPIC_API_KEY", "TAVILY_API_KEY", "TYPESAFE_API_KEY"}}
            env["PPA_MCP_TOKEN"] = settings.mcp_token
            env.setdefault("PPA_HOME", str(DATA_DIR / "ppa_home"))   # connection secrets stay local
            env.setdefault("PPA_GENERATED_CALENDAR", "1")            # set it to 0 for invitations only
            # What is written to the practice workspace is kept, so a restart loses nothing.
            env.setdefault("PPA_PRACTICE_STATE", str(DATA_DIR / "practice_state.json"))
            self.process = subprocess.Popen(
                [sys.executable, str(settings.gateway_script), "--host", settings.mcp_host,
                 "--port", str(settings.mcp_port)], env=env, stdout=log, stderr=subprocess.STDOUT)
            self.owned = True
            for _ in range(240):
                if self.process.poll() is not None:
                    self.error = (f"The gateway exited with code {self.process.returncode}. "
                                  f"See {DATA_DIR / 'gateway.log'}")
                    raise WorkspaceError(self.error)
                if await self.probe() is not None:
                    break
                await asyncio.sleep(0.25)
            else:
                self.error = "The gateway did not become healthy within 60 seconds"
                raise WorkspaceError(self.error)
        return await self.refresh()

    async def refresh(self) -> dict[str, Any]:
        """Re-read health, tools and the owner. Called at start and after a connection change."""
        from langchain_mcp_adapters.client import MultiServerMCPClient

        if await self.probe() is None:
            self.ready, self.error = False, "The workspace gateway is not reachable"
            raise WorkspaceError(self.error)
        payload = await self._admin("GET", "/admin/world")
        world.load(payload)
        self.provenance = payload.get("provenance")
        client = MultiServerMCPClient({
            name: {"transport": "streamable_http", "url": f"{settings.mcp_base_url}/{name}/mcp",
                   "headers": {"Authorization": f"Bearer {settings.mcp_token}"}}
            for name in SYSTEMS}, handle_tool_errors=False)
        self.tools, self.offered = {}, {}
        for name in SYSTEMS:
            self.offered[name] = []
            for tool in await client.get_tools(server_name=name):
                self.tools[tool.name] = tool
                schema = tool.args_schema if isinstance(tool.args_schema, dict) \
                    else tool.args_schema.model_json_schema()
                self.offered[name].append({
                    "name": tool.name, "description": tool.description, "input_schema": schema,
                    "tier": ALLOWLIST.get(tool.name, "never"), "exposed": tool.name in ALLOWLIST,
                    "read": tool.name in READ_TOOLS})
        self._cache.clear()
        self.ready, self.error = True, None
        return self.status()

    def _terminate(self) -> None:
        if self.owned and self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._terminate()
        self.ready = False

    # ── Tools ────────────────────────────────────────────────────────────────

    def tier(self, name: str) -> str:
        return ALLOWLIST.get(name, "never")

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call one allowlisted gateway tool and return its parsed result."""
        if name not in ALLOWLIST:
            raise ToolNotAllowed(f"{name} is not on the harness allowlist")
        tool = self.tools.get(name)
        if tool is None:
            raise WorkspaceError(f"The gateway does not offer {name}")
        arguments = {key: value for key, value in (arguments or {}).items() if value is not None}
        key = name + json.dumps(arguments, sort_keys=True, default=str)
        log, system = call_log.get(), name.split("_", 1)[0]
        if name in READ_TOOLS:
            hit = self._cache.get(key)
            if hit and hit[0] > time.monotonic():
                entry = {"tool": name, "system": system, "ms": 0.0, "ok": True, "cached": True}
                if log is not None:
                    log.append(entry)
                _remember_call(entry, arguments, hit[1])
                return hit[1]
        else:
            self._cache.clear()
        started, ok, result = time.perf_counter(), False, None
        try:
            result = parse_result(await tool.ainvoke(arguments))
            ok = "error" not in result
        except Exception as exc:        # the MCP adapter raises its own error types
            raise WorkspaceError(f"{name} failed: {str(exc)[:300]}") from exc
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            entry = {"tool": name, "system": system, "ms": elapsed, "ok": ok, "cached": False}
            if log is not None:
                log.append(entry)
            _remember_call(entry, arguments, result)
            bus.publish("mcp", **entry)
        if name in READ_TOOLS and ok:
            self._cache[key] = (time.monotonic() + READ_CACHE_SECONDS, result)   # never stored
        return result

    def forget_reads(self) -> None:
        self._cache.clear()

    def catalogue(self) -> dict[str, list[dict[str, Any]]]:
        return self.offered

    # ── Operator API (plain HTTP, so a model can never reach it) ─────────────

    async def _admin(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        try:
            response = await self._http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise WorkspaceError(f"The gateway is not reachable ({type(exc).__name__})") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code == 401:
            raise WorkspaceError("The gateway rejected the token. Another gateway may hold this port.")
        if response.status_code >= 400:
            raise WorkspaceError(str(payload.get("error") or f"The gateway answered {response.status_code}"))
        return payload

    async def systems(self) -> dict[str, Any]:
        await self.probe()
        return self.health.get("systems", {})

    def practising(self) -> bool:
        return self.health.get("mode") == "practice"

    async def providers(self) -> dict[str, Any]:
        return await self._admin("GET", "/admin/providers")

    async def connect(self, system: str, provider: str, provider_settings: dict[str, Any]) -> dict[str, Any]:
        """Hand credentials to the gateway. They are never kept, logged or echoed by the harness."""
        result = await self._admin("POST", "/admin/connect",
                                   {"system": system, "provider": provider, "settings": provider_settings})
        result.pop("settings", None)
        return result

    async def disconnect(self, system: str) -> dict[str, Any]:
        return await self._admin("POST", "/admin/disconnect", {"system": system})

    async def safe_mode(self) -> bool:
        await self.probe()
        return bool(self.health.get("safe_mode", True))

    async def set_safe_mode(self, enabled: bool) -> bool:
        result = await self._admin("POST", "/admin/safe_mode", {"enabled": enabled})
        self.health["safe_mode"] = bool(result.get("safe_mode", enabled))
        bus.publish("safe_mode", enabled=self.health["safe_mode"])
        return self.health["safe_mode"]

    async def set_clock(self, now: str | None) -> str:
        """Move the practice clock. Mail arrives and meetings are announced as the clock advances."""
        result = await self._admin("POST", "/admin/clock", {"now": now})
        self._cache.clear()
        return result["clock"]

    async def effects(self) -> list[dict[str, Any]]:
        return (await self._admin("GET", "/admin/effects")).get("effects", [])

    async def overlay(self) -> str:
        response = await self._http.get("/admin/overlay.ics")
        response.raise_for_status()
        return response.text

    async def reset(self) -> dict[str, Any]:
        self._cache.clear()
        return await self._admin("POST", "/admin/reset", {})

    def status(self) -> dict[str, Any]:
        return {"ready": self.ready, "error": self.error, "url": settings.mcp_base_url,
                "transport": "MCP over streamable HTTP", "launched_by_appbook": self.owned,
                "pid": self.process.pid if self.process and self.process.poll() is None else None,
                "mode": self.health.get("mode"), "safe_mode": self.health.get("safe_mode"),
                "owner": self.health.get("owner"), "systems": self.health.get("systems", {}),
                "clock_is_pinned": self.health.get("clock_is_pinned"),
                "servers": {name: f"{settings.mcp_base_url}/{name}/mcp" for name in SYSTEMS},
                "tools_offered": sum(len(items) for items in self.offered.values()),
                "tools_allowlisted": len(ALLOWLIST), "provenance": self.provenance,
                "read_cache_seconds": READ_CACHE_SECONDS}


workspace = Workspace()
