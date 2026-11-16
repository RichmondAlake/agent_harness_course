"""One in-process event bus for the browser.

Run progress, timers, notifications and table activity all travel over a single
Server-Sent Events stream. ``publish`` is safe to call from the scheduler
thread as well as from request handlers.
"""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._recent: deque[dict[str, Any]] = deque(maxlen=400)
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._sequence = 0

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server's event loop so other threads can hand events to it."""
        self._loop = loop

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def publish(self, topic: str, /, **data: Any) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {"sequence": self._sequence, "topic": topic, "data": data,
                     "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}
            self._recent.appendleft(event)
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._fan_out, event)
        return event

    def _fan_out(self, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():            # a slow browser loses its oldest event, never blocks a run
                queue.get_nowait()
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def recent(self, topic: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        items = [item for item in self._recent if topic is None or item["topic"] == topic]
        return items[: min(max(limit, 1), 200)]

    def status(self) -> dict[str, int]:
        """How many browsers are listening and how many events have been published."""
        return {"listeners": len(self._subscribers), "published": self._sequence}


bus = EventBus()
