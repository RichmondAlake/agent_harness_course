"""Settings from the repository .env, an event bus, and a read-only explorer for the appbook."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ADVANCED = BACKEND.parents[2]
REPOSITORY = ADVANCED.parents[1]


def load_env() -> None:
    """The repository .env, without overriding what the shell already set."""
    for candidate in (REPOSITORY / ".env", ADVANCED / ".env"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def add_paths(backend: Path) -> None:
    for folder in (str(backend),):
        if folder not in sys.path:
            sys.path.insert(0, folder)


class Bus:
    """Events from harness threads to browser sessions, as server-sent events."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()
        self.recent: list[dict] = []

    def publish(self, topic: str, **data: Any) -> None:
        event = {"topic": topic, **data}
        self.recent = [*self.recent[-199:], event]
        if self.loop is None:
            return
        for queue in list(self.queues):
            self.loop.call_soon_threadsafe(queue.put_nowait, event)

    async def stream(self):
        queue: asyncio.Queue = asyncio.Queue()
        self.queues.add(queue)
        try:
            while True:
                event = await queue.get()
                yield {"event": event["topic"], "data": json.dumps(event, default=str)}
        finally:
            self.queues.discard(queue)


SAFE_NAME = re.compile(r"^[A-Z][A-Z0-9_$#]{0,127}$")


def explorer_tables(prefixes: tuple[str, ...]) -> list[dict]:
    """The tables the appbook may show, with their row counts."""
    from shared.oracle import rows
    found = rows("SELECT table_name FROM user_tables ORDER BY table_name")
    listed = []
    for row in found:
        name = row["table_name"]
        if name.startswith(prefixes) or name.startswith("CHECKPOINT"):
            count = rows(f"SELECT COUNT(*) AS n FROM {name}")[0]["n"]
            listed.append({"name": name, "rows": count})
    return listed


def explorer_rows(name: str, prefixes: tuple[str, ...], limit: int = 50, offset: int = 0, search: str = "") -> dict:
    """Newest rows of one table. Names come from the dictionary; values are bound; long cells are cut."""
    from shared.oracle import rows
    name = name.upper()
    allowed = {t["name"] for t in explorer_tables(prefixes)}
    if not SAFE_NAME.match(name) or name not in allowed:
        raise KeyError(name)
    columns = rows("SELECT column_name, data_type FROM user_tab_columns WHERE table_name = :t ORDER BY column_id",
                   {"t": name})
    textual = [c["column_name"] for c in columns if c["data_type"] in ("VARCHAR2", "CHAR")]
    where, binds = "", {"limit": min(max(limit, 1), 200), "offset": max(offset, 0)}
    if search and textual:
        where = " WHERE " + " OR ".join(f"UPPER({c}) LIKE :q" for c in textual)
        binds["q"] = f"%{search.upper()}%"
    select = ", ".join(
        f"SUBSTR({c['column_name']}, 1, 300) AS {c['column_name']}" if c["data_type"] == "CLOB"
        else f"'<vector>' AS {c['column_name']}" if c["data_type"] == "VECTOR"
        else f"'<blob>' AS {c['column_name']}" if c["data_type"] == "BLOB"
        else c["column_name"] for c in columns)
    found = rows(f"SELECT {select} FROM {name}{where} ORDER BY ROWID DESC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY", binds)
    total = rows(f"SELECT COUNT(*) AS n FROM {name}{where}", {k: v for k, v in binds.items() if k == "q"})[0]["n"]
    return {"table": name, "columns": [{"name": c["column_name"], "type": c["data_type"]} for c in columns],
            "rows": [{k: (str(v)[:300] if v is not None else None) for k, v in r.items()} for r in found],
            "total": total, "limit": binds["limit"], "offset": binds["offset"]}
