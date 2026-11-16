"""In-app notifications: stored in ``ppa_notifications`` and pushed to the browser over SSE."""
from __future__ import annotations

from typing import Any

from backend.core import clock, store
from backend.core.events import bus


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "payload": store.loads(item["payload"], {})}


def notify(kind: str, title: str, body: str, *, payload: dict | None = None,
           job_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    item = {"notification_id": store.new_id("N"), "kind": kind, "title": title, "body": body,
            "payload": store.dumps(payload or {}), "job_id": job_id, "run_id": run_id,
            "created_at": clock.stamp(), "real_created_at": store.real_now(), "read_at": None}
    store.execute("INSERT INTO ppa_notifications VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(item.values()))
    shaped = _shape(item)
    bus.publish("notification", **shaped)
    return shaped


def recent(limit: int = 30) -> list[dict[str, Any]]:
    return [_shape(item) for item in store.rows(
        "SELECT * FROM ppa_notifications ORDER BY rowid DESC LIMIT ?", (limit,))]


def get(notification_id: str | None) -> dict[str, Any] | None:
    if not notification_id:
        return None
    found = store.row("SELECT * FROM ppa_notifications WHERE notification_id=?", (notification_id,))
    return _shape(found) if found else None


def mark_read(notification_id: str) -> int:
    return store.execute("UPDATE ppa_notifications SET read_at=? WHERE notification_id=? AND read_at IS NULL",
                         (clock.stamp(), notification_id))


def unread() -> int:
    return store.row("SELECT COUNT(*) AS total FROM ppa_notifications WHERE read_at IS NULL")["total"]
