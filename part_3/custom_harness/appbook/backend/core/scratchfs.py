"""The workday scratch pad: session-scoped files that are cheap to write.

A workday is one session. Quick captures land in ``/inbox``, the day plan in
``/plans/today.md``, working notes in ``/notes``. Nothing here is durable
until the session ends: files marked for promotion are staged into a queue,
deduplicated by content hash, and promoted into ``ppa_tasks`` or long-term
memory. The rest is left behind.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from backend.core import clock, store, tasks, world
from backend.core.memory import content_hash, memory_provider

DIRECTORIES = ("/inbox", "/plans", "/notes", "/tool_out")
PLAN_PATH = "/plans/today.md"
TARGETS = ("task", "memory")


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "meta": store.loads(item["meta"], {}), "is_dir": bool(item["is_dir"]),
            "promote_on_end": bool(item["promote_on_end"])}


class ScratchFS:
    """A narrow POSIX-like interface scoped to one workday session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    @staticmethod
    def _clean(path: str) -> str:
        requested = PurePosixPath("/" + str(path).strip().strip("/"))
        if ".." in requested.parts:
            raise ValueError("Scratch paths cannot leave the session")
        return str(requested)

    def mkdir(self, path: str) -> None:
        stamp = clock.stamp()
        store.execute(
            "INSERT OR IGNORE INTO ppa_scratch_files(session_id,path,is_dir,kind,created_at,updated_at) "
            "VALUES (?,?,1,'dir',?,?)", (self.session_id, self._clean(path), stamp, stamp))

    def write(self, path: str, content: str, *, kind: str = "note", meta: dict | None = None,
              promote_on_end: bool = False, promote_target: str = "memory") -> dict[str, Any]:
        if promote_target not in TARGETS:
            raise ValueError(f"promote_target must be one of {', '.join(TARGETS)}")
        clean, stamp = self._clean(path), clock.stamp()
        store.execute(
            """INSERT INTO ppa_scratch_files
               (session_id,path,is_dir,content,kind,meta,promote_on_end,promote_target,
                promotion_state,created_at,updated_at)
               VALUES (?,?,0,?,?,?,?,?,'N',?,?)
               ON CONFLICT(session_id,path) DO UPDATE SET
                 is_dir=0,content=excluded.content,kind=excluded.kind,meta=excluded.meta,
                 promote_on_end=excluded.promote_on_end,promote_target=excluded.promote_target,
                 promotion_state='N',updated_at=excluded.updated_at""",
            (self.session_id, clean, content, kind, store.dumps(meta or {}), int(promote_on_end),
             promote_target, stamp, stamp))
        return {"path": clean, "bytes": len(content.encode()), "promote_on_end": promote_on_end,
                "promote_target": promote_target}

    def read(self, path: str) -> str:
        found = store.row("SELECT content FROM ppa_scratch_files WHERE session_id=? AND path=? AND is_dir=0",
                          (self.session_id, self._clean(path)))
        if found is None:
            raise FileNotFoundError(self._clean(path))
        return found["content"]

    def exists(self, path: str) -> bool:
        return store.row("SELECT 1 FROM ppa_scratch_files WHERE session_id=? AND path=? AND is_dir=0",
                         (self.session_id, self._clean(path))) is not None

    def append(self, path: str, content: str, **options: Any) -> dict[str, Any]:
        prior = self.read(path) if self.exists(path) else ""
        return self.write(path, prior + content, **options)

    def files(self, root: str = "/") -> list[dict[str, Any]]:
        prefix = self._clean(root).rstrip("/") + "/%"
        return [_shape(item) for item in store.rows(
            "SELECT * FROM ppa_scratch_files WHERE session_id=? AND path LIKE ? AND is_dir=0 "
            "ORDER BY path", (self.session_id, prefix))]

    def flag(self, path: str, *, promote: bool, target: str | None = None) -> dict[str, Any]:
        """Choose whether a file is promoted when the workday ends, and where to."""
        if target is not None and target not in TARGETS:
            raise ValueError(f"target must be one of {', '.join(TARGETS)}")
        clean = self._clean(path)
        changed = store.execute(
            "UPDATE ppa_scratch_files SET promote_on_end=?,promote_target=COALESCE(?,promote_target) "
            "WHERE session_id=? AND path=? AND is_dir=0", (int(promote), target, self.session_id, clean))
        if not changed:
            raise FileNotFoundError(clean)
        return _shape(store.row("SELECT * FROM ppa_scratch_files WHERE session_id=? AND path=?",
                                (self.session_id, clean)))

    def delete(self, path: str) -> int:
        return store.execute("DELETE FROM ppa_scratch_files WHERE session_id=? AND path=? AND is_dir=0",
                             (self.session_id, self._clean(path)))


def begin_session(session_id: str | None = None) -> ScratchFS:
    """Start or resume a workday session and create its standard directories."""
    session_id = session_id or clock.session_id()
    store.execute(
        """INSERT INTO ppa_agent_sessions(session_id,user_id,status,started_at) VALUES (?,?,'ACTIVE',?)
           ON CONFLICT(session_id) DO UPDATE SET status='ACTIVE',ended_at=NULL""",
        (session_id, world.user_id(), clock.stamp()))
    filesystem = ScratchFS(session_id)
    for directory in DIRECTORIES:
        filesystem.mkdir(directory)
    return filesystem


def capture(text: str, *, session_id: str | None = None, kind: str = "capture",
            focus_session_id: str | None = None) -> dict[str, Any]:
    """Quick capture into ``/inbox``. Promoted into a task when the workday ends, unless unticked."""
    text = text.strip()
    if not text:
        raise ValueError("Nothing to capture")
    filesystem = begin_session(session_id)
    sequence = len(filesystem.files("/inbox")) + 1
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "note"
    written = filesystem.write(
        f"/inbox/{sequence:03d}-{slug}.md", text, kind=kind,
        meta={"focus_session_id": focus_session_id, "captured_at": clock.stamp()},
        promote_on_end=True, promote_target="task")
    return {**written, "session_id": filesystem.session_id, "kind": kind, "text": text,
            "focus_session_id": focus_session_id}


def distractions(focus_session_id: str) -> list[dict[str, Any]]:
    """Notes captured while a focus session ran, surfaced at its break."""
    found = store.rows("SELECT * FROM ppa_scratch_files WHERE kind='distraction' AND is_dir=0 ORDER BY rowid")
    return [_shape(item) for item in found
            if store.loads(item["meta"], {}).get("focus_session_id") == focus_session_id]


def session(session_id: str | None = None) -> dict[str, Any]:
    session_id = session_id or clock.session_id()
    found = store.row("SELECT * FROM ppa_agent_sessions WHERE session_id=?", (session_id,))
    files = ScratchFS(session_id).files("/")
    return {"session_id": session_id, "status": found["status"] if found else "NOT_STARTED",
            "started_at": found["started_at"] if found else None,
            "ended_at": found["ended_at"] if found else None,
            "files": files, "inbox": [item for item in files if item["path"].startswith("/inbox/")],
            "plan": next((item["content"] for item in files if item["path"] == PLAN_PATH), ""),
            "promotion_states": "N = working, S = staged, Y = promoted, D = duplicate"}


def stage_session_end(session_id: str) -> int:
    """ACTIVE to ENDED: stage every file marked for promotion, chunked and hashed."""
    stamp = clock.stamp()
    store.execute("UPDATE ppa_agent_sessions SET status='ENDED',ended_at=? "
                  "WHERE session_id=? AND status<>'ENDED'", (stamp, session_id))
    staged = store.rows(
        "SELECT * FROM ppa_scratch_files WHERE session_id=? AND is_dir=0 AND promote_on_end=1 "
        "AND promotion_state='N' ORDER BY path", (session_id,))
    for item in staged:
        chunk = item["content"].strip()
        store.execute(
            "INSERT INTO ppa_memory_promotion_queue(session_id,path,target,chunk,content_hash,staged_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, item["path"], item["promote_target"], chunk, content_hash(chunk), stamp))
        store.execute("UPDATE ppa_scratch_files SET promotion_state='S' WHERE session_id=? AND path=?",
                      (session_id, item["path"]))
    return len(staged)


def drain_promotion_queue() -> list[dict[str, Any]]:
    """Promote staged chunks. A hash that was promoted before is a duplicate, not a second row."""
    outcomes = []
    for item in store.rows("SELECT * FROM ppa_memory_promotion_queue WHERE consumed='N' ORDER BY queue_id"):
        earlier = store.row(
            "SELECT outcome_ref FROM ppa_memory_promotion_queue WHERE consumed='Y' AND outcome='PROMOTED' "
            "AND target=? AND content_hash=? ORDER BY queue_id", (item["target"], item["content_hash"]))
        if earlier:
            outcome, reference = "DUPLICATE", earlier["outcome_ref"]
        elif item["target"] == "task":
            made = tasks.add(item["chunk"].splitlines()[0][:160], source_type="capture",
                             source_ref=f"scratch:{item['session_id']}{item['path']}")
            outcome = "PROMOTED" if made["status"] == "created" else "DUPLICATE"
            reference = made["task"]["task_id"]
        else:
            made = memory_provider.write("fact", item["chunk"], metadata={
                "source": "scratch_promotion", "session_id": item["session_id"], "path": item["path"]})
            outcome = "DUPLICATE" if made["deduplicated"] else "PROMOTED"
            reference = made["memory_id"]
        store.execute("UPDATE ppa_memory_promotion_queue SET consumed='Y',outcome=?,outcome_ref=?,"
                      "consumed_at=? WHERE queue_id=?", (outcome, reference, clock.stamp(), item["queue_id"]))
        store.execute("UPDATE ppa_scratch_files SET promotion_state=? WHERE session_id=? AND path=?",
                      ("Y" if outcome == "PROMOTED" else "D", item["session_id"], item["path"]))
        outcomes.append({"path": item["path"], "target": item["target"], "outcome": outcome,
                         "reference": reference, "content_hash": item["content_hash"][:12]})
    return outcomes


def _episode(session_id: str, carried: list[dict[str, Any]]) -> str:
    """A plain record of the day, built from what the harness actually did."""
    day = session_id.removeprefix("workday-")
    runs = store.row("SELECT COUNT(*) AS total FROM ppa_agent_runs WHERE session_id=?", (session_id,))
    created = store.row("SELECT COUNT(*) AS total FROM ppa_tasks WHERE created_at LIKE ?", (day + "%",))
    done = store.rows("SELECT title FROM ppa_tasks WHERE status='DONE' AND completed_at LIKE ?", (day + "%",))
    focus = store.row("SELECT COUNT(*) AS total, COALESCE(SUM(actual_minutes),0) AS minutes "
                      "FROM ppa_focus_sessions WHERE workday_session_id=?", (session_id,))
    decisions = store.rows("SELECT state, COUNT(*) AS total FROM ppa_action_audit "
                           "WHERE session_id=? AND tier='approval' GROUP BY state", (session_id,))
    parts = [f"Workday {day}: {runs['total']} assistant runs, {created['total']} tasks created, "
             f"{len(done)} completed, {focus['total']} focus sessions ({focus['minutes']} minutes)."]
    if done:
        parts.append("Completed: " + "; ".join(item["title"] for item in done[:5]) + ".")
    if carried:
        parts.append("Carried over: " + "; ".join(item["title"] for item in carried[:5]) + ".")
    if decisions:
        parts.append("Gated actions: " + ", ".join(
            f"{item['total']} {item['state'].lower()}" for item in decisions) + ".")
    return " ".join(parts)


def end_session(session_id: str | None = None) -> dict[str, Any]:
    """End the workday: promote what was chosen, count the slips, write the episode."""
    session_id = session_id or clock.session_id()
    begin = store.row("SELECT status FROM ppa_agent_sessions WHERE session_id=?", (session_id,))
    already_ended = bool(begin) and begin["status"] == "ENDED"
    if begin is None:
        begin_session(session_id)
    staged = stage_session_end(session_id)
    outcomes = drain_promotion_queue()
    carried = [] if already_ended else tasks.carry_over(session_id.removeprefix("workday-"))
    summary = _episode(session_id, carried)
    episode = memory_provider.write("episode", summary, metadata={"source": "session_end",
                                                                  "session_id": session_id})
    store.execute("UPDATE ppa_agent_sessions SET summary=? WHERE session_id=?", (summary, session_id))
    return {"session_id": session_id, "status": "ENDED", "staged": staged, "outcomes": outcomes,
            "promoted": sum(item["outcome"] == "PROMOTED" for item in outcomes),
            "duplicates": sum(item["outcome"] == "DUPLICATE" for item in outcomes),
            "carried_over": carried, "episode": episode}


def status() -> dict[str, Any]:
    return {"implementation": "ScratchFS on the local store", "session": session(),
            "directories": DIRECTORIES,
            "promotion": "workday end -> staged chunks -> content-hash dedupe -> ppa_tasks or memory",
            "queue": store.rows("SELECT * FROM ppa_memory_promotion_queue ORDER BY queue_id DESC LIMIT 20")}
