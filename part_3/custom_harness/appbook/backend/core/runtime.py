"""Start, stop and rebind the harness as one unit.

The order matters: the gateway supplies the owner, the owner names the
database file, the database holds the registries and the checkpoints, and the
scheduler re-arms whatever that database says is still pending.
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.core import (clock, llm_client, routines, skills, store, system_one, tools, tracing,
                          websearch, world)
from backend.core.agent import agent
from backend.core.events import bus
from backend.core.memory import memory_provider
from backend.core.scheduler import scheduler
from backend.core.workspace import workspace

_state: dict[str, Any] = {"task": None, "ready": False, "error": None}
KINDS = ("pomodoro", "morning_brief", "end_of_day_wrap", "weekly_review", "meeting_prep", "vip_alert")


PRACTICE_CLOCK_KEY = "practice_clock"


async def _bind() -> None:
    """Attach everything that depends on who the owner is."""
    store.initialize()
    moved = store.get_meta(PRACTICE_CLOCK_KEY)
    if moved and workspace.practising():
        # The gateway starts at the scenario's first moment; the harness remembers where the clock was.
        world.set_scenario_now(await workspace.set_clock(moved))
        await workspace.probe()
    skills.sync_registry()
    tools.sync_registry()
    await agent.start()
    for kind in KINDS:
        scheduler.register(kind, routines.handle)
    scheduler.watch(routines.evaluate_triggers)
    scheduler.start()


async def _start() -> None:
    try:
        bus.bind(asyncio.get_running_loop())
        await workspace.start()
        await _bind()
        _state.update(ready=True, error=None)
    except Exception as exc:
        _state.update(ready=False, error=f"{type(exc).__name__}: {exc}")
        await stop()            # leave no gateway, thread or connection behind
        raise


def warm() -> asyncio.Task:
    """Begin start-up without blocking the server, so the page loads at once."""
    _state["task"] = asyncio.create_task(_start())
    return _state["task"]


async def ready() -> None:
    """Wait for start-up. Raises with the reason when the harness could not start."""
    task = _state["task"]
    if task is None:
        raise RuntimeError("The harness has not been started")
    await asyncio.shield(task)


async def stop() -> None:
    scheduler.stop()
    await agent.stop()
    await workspace.stop()
    _state.update(ready=False)


async def rebind() -> dict[str, Any]:
    """After a connection change: a different owner means a different state file and clock."""
    scheduler.stop()
    await workspace.refresh()
    await _bind()
    bus.publish("workspace", **await connection_status())
    return status()


async def set_clock(value: str | None, *, evaluate: bool = True) -> dict[str, Any]:
    """Move the clock. In practice the gateway owns it and replays the mailbox against it."""
    if value:
        value = clock.localise(value).isoformat(timespec="minutes")     # raises on a moment that cannot be read
    if workspace.practising():
        world.set_scenario_now(await workspace.set_clock(value))
        store.set_meta(PRACTICE_CLOCK_KEY, world.scenario_now() if value else None)
        await workspace.probe()
    else:
        clock.pin(value)
    scheduler.sync_schedules()
    if evaluate and scheduler.automation_enabled():
        await routines.evaluate_triggers()
    state = clock.status()
    bus.publish("clock", **state)
    return state


async def reset() -> dict[str, Any]:
    """Empty the harness state for this owner and, in practice, restore the workspace."""
    scheduler.stop()
    if workspace.practising():
        await workspace.reset()
    await agent.stop()
    store.reset()
    system_one.forget()
    clock.pin(None)
    await workspace.refresh()
    await _bind()
    bus.publish("reset", clock=clock.status())
    return status()


async def connection_status() -> dict[str, Any]:
    systems = await workspace.systems()
    return {"mode": workspace.health.get("mode"), "practice": workspace.practising(),
            "safe_mode": bool(workspace.health.get("safe_mode", True)),
            "owner": workspace.health.get("owner"), "systems": systems}


def status() -> dict[str, Any]:
    """The header's view: who, where, which clock, which responder."""
    if not _state["ready"]:
        return {"ready": False, "warming": _state["error"] is None, "error": _state["error"]}
    persona = world.persona()
    return {"ready": True, "owner": {key: persona[key] for key in ("name", "email", "timezone")},
            "workspace": {"mode": workspace.health.get("mode"), "practice": workspace.practising(),
                          "safe_mode": bool(workspace.health.get("safe_mode", True)),
                          "systems": workspace.health.get("systems", {}),
                          "provenance": workspace.provenance},
            "clock": clock.status(), "responder": llm_client.status(),
            "substrate": store.SUBSTRATE, "memory": memory_provider.name,
            "web_search": websearch.status(), "tracing": tracing.status(),
            "automation": scheduler.automation_enabled()}
