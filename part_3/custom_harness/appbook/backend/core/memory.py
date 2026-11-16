"""Long-term and episodic memory behind one small provider interface.

The appbook ships ``LocalMemoryProvider``, a SQLite teaching mirror. The
notebook uses Oracle Agent Memory; a provider for it plugs in here by
implementing ``MemoryProvider`` and being returned from ``build_provider``.
Memory starts empty and grows only from what the user states or confirms.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Protocol

from backend.config import settings
from backend.core import clock, store, world

MEMORY_TYPES = ("preference", "guideline", "fact", "person", "commitment", "episode")
# Preferences and guidelines last until changed. Everything else fades.
DEFAULT_TTL_DAYS: dict[str, int | None] = {
    "preference": None, "guideline": None, "fact": 180, "person": 365, "commitment": 30, "episode": 30}
_STOP = frozenset("a an and are as at be before by do for from i in is it know me my of on or "
                  "should so that the this to what when which with you your".split())


def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def keywords(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9#]+", text.lower()) if word not in _STOP and len(word) > 1}


class MemoryProvider(Protocol):
    name: str
    implementation: str

    def write(self, memory_type: str, content: str, *, metadata: dict | None = None,
              ttl_days: int | None = None) -> dict[str, Any]: ...

    def recall(self, query: str, *, limit: int = 8,
               memory_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]: ...

    def standing(self) -> list[dict[str, Any]]: ...

    def list(self) -> dict[str, list[dict[str, Any]]]: ...

    def update(self, memory_id: str, content: str, ttl_days: int | None = None) -> dict[str, Any]: ...

    def delete(self, memory_id: str) -> int: ...

    def sweep(self) -> list[dict[str, Any]]: ...

    def status(self) -> dict[str, Any]: ...


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "metadata": store.loads(item["metadata"], {})}


class LocalMemoryProvider:
    """Typed memories in ``ppa_memories`` with keyword recall, hash dedupe and TTLs."""

    name = "local"
    implementation = "Local provider with the same contract as Oracle Agent Memory"

    def _expiry(self, memory_type: str, ttl_days: int | None) -> str | None:
        days = ttl_days if ttl_days is not None else DEFAULT_TTL_DAYS[memory_type]
        return (clock.now() + timedelta(days=days)).isoformat(timespec="seconds") if days else None

    def write(self, memory_type: str, content: str, *, metadata: dict | None = None,
              ttl_days: int | None = None) -> dict[str, Any]:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"memory_type must be one of {', '.join(MEMORY_TYPES)}")
        content = " ".join(content.split())
        if not content:
            raise ValueError("A memory needs content")
        digest = content_hash(content)
        duplicate = store.row(
            "SELECT * FROM ppa_memories WHERE user_id=? AND content_hash=? AND status='ACTIVE'",
            (world.user_id(), digest))
        if duplicate:
            return {**_shape(duplicate), "deduplicated": True}
        stamp = clock.stamp()
        item = {"memory_id": store.new_id("MEM"), "user_id": world.user_id(), "memory_type": memory_type,
                "content": content, "content_hash": digest, "metadata": store.dumps(metadata or {}),
                "status": "ACTIVE", "created_at": stamp, "updated_at": stamp,
                "expires_at": self._expiry(memory_type, ttl_days), "last_used_at": None, "use_count": 0}
        store.execute("INSERT INTO ppa_memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tuple(item.values()))
        return {**_shape(item), "deduplicated": False}

    def _active(self, memory_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        now = clock.stamp()
        found = store.rows(
            "SELECT * FROM ppa_memories WHERE user_id=? AND status='ACTIVE' "
            "AND (expires_at IS NULL OR expires_at > ?) ORDER BY rowid", (world.user_id(), now))
        return [_shape(item) for item in found if not memory_types or item["memory_type"] in memory_types]

    def recall(self, query: str, *, limit: int = 8,
               memory_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        wanted = keywords(query)
        scored = []
        for position, item in enumerate(self._active(memory_types)):
            score = len(wanted & keywords(item["content"]))
            if score:
                scored.append((score, position, item))
        scored.sort(key=lambda entry: (-entry[0], -entry[1]))
        chosen = [{**item, "score": score} for score, _, item in scored[:limit]]
        for item in chosen:
            store.execute("UPDATE ppa_memories SET use_count=use_count+1,last_used_at=? WHERE memory_id=?",
                          (clock.stamp(), item["memory_id"]))
        return chosen

    def standing(self) -> list[dict[str, Any]]:
        """Preferences and guidelines are few and always apply, so they are always in context."""
        return self._active(("preference", "guideline"))

    def list(self) -> dict[str, list[dict[str, Any]]]:
        found = store.rows("SELECT * FROM ppa_memories WHERE user_id=? ORDER BY rowid DESC",
                           (world.user_id(),))
        grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in MEMORY_TYPES}
        for item in found:
            grouped[item["memory_type"]].append(_shape(item))
        return grouped

    def update(self, memory_id: str, content: str, ttl_days: int | None = None) -> dict[str, Any]:
        current = store.row("SELECT * FROM ppa_memories WHERE memory_id=?", (memory_id,))
        if current is None:
            raise KeyError(memory_id)
        content = " ".join(content.split())
        store.execute(
            "UPDATE ppa_memories SET content=?,content_hash=?,updated_at=?,expires_at=?,status='ACTIVE' "
            "WHERE memory_id=?",
            (content, content_hash(content), clock.stamp(),
             self._expiry(current["memory_type"], ttl_days), memory_id))
        return _shape(store.row("SELECT * FROM ppa_memories WHERE memory_id=?", (memory_id,)))

    def delete(self, memory_id: str) -> int:
        return store.execute("DELETE FROM ppa_memories WHERE memory_id=?", (memory_id,))

    def sweep(self) -> list[dict[str, Any]]:
        """Mark memories whose time to live has passed. Expired rows stay visible, never recalled."""
        due = store.rows(
            "SELECT * FROM ppa_memories WHERE user_id=? AND status='ACTIVE' AND expires_at IS NOT NULL "
            "AND expires_at <= ?", (world.user_id(), clock.stamp()))
        for item in due:
            store.execute("UPDATE ppa_memories SET status='EXPIRED',updated_at=? WHERE memory_id=?",
                          (clock.stamp(), item["memory_id"]))
        return [_shape(item) for item in due]

    def status(self) -> dict[str, Any]:
        grouped = self.list()
        requested = settings.memory_backend
        return {"provider": self.name, "implementation": self.implementation,
                "requested_backend": requested,
                "note": None if requested == self.name else
                f"Backend '{requested}' is not part of this appbook build; the local provider is in use.",
                "recall": "keyword overlap, newest first; standing preferences and guidelines always apply",
                "counts": {kind: len(items) for kind, items in grouped.items()},
                "ttl_days": DEFAULT_TTL_DAYS}


def build_provider() -> MemoryProvider:
    """The seam for other backends. Only the local provider ships with the appbook."""
    return LocalMemoryProvider()


memory_provider: MemoryProvider = build_provider()


def expires_in_days(item: dict[str, Any], now: datetime) -> int | None:
    if not item.get("expires_at"):
        return None
    return (datetime.fromisoformat(item["expires_at"]) - now).days
