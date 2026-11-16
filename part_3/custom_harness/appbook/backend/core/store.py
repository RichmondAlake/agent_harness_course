"""The harness substrate: Oracle AI Database, or a local file when there is no database.

The harness keeps its state in one set of tables: ``PPA_*`` tables, a promotion
queue, an automation queue and LangGraph's checkpoints. Every module reads and
writes them through ``rows``, ``row``, ``execute`` and ``connect`` below.

Two substrates can sit under those four functions.

* **Oracle AI Database.** Each owner has a schema. This is what the appbook uses
  when the database answers.
* **Local store.** One file per owner, for a machine with no database.

``PPA_SUBSTRATE`` chooses: ``oracle``, ``local`` or ``auto`` (the default, which
takes Oracle when it is reachable). Harness-owned state starts empty either way:
tasks, focus sessions, memories and notes exist only once the assistant or the
user creates them.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.config import DATA_DIR
from backend.core import oracle_store, world
from backend.core.events import bus

# The one place that names the store to a person. It changes when the substrate changes.
SUBSTRATE = "Local store"
_lock = threading.RLock()
_state: dict[str, Any] = {"ready": False, "error": None, "path": None, "kind": "local", "note": ""}
_route = threading.local()
_quiet: ContextVar[bool] = ContextVar("ppa_quiet_reads", default=False)
_writes: dict[str, int] = {}          # writes per table since start-up, for the explorer's change marks

SCHEMA = """
CREATE TABLE IF NOT EXISTS ppa_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_contacts (
  email TEXT PRIMARY KEY, contact_id TEXT NOT NULL, name TEXT NOT NULL,
  organisation TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '',
  relationship TEXT NOT NULL DEFAULT '', is_vip INTEGER NOT NULL DEFAULT 0,
  vip_source TEXT NOT NULL DEFAULT '', messages_sent INTEGER NOT NULL DEFAULT 0, synced_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_tasks (
  task_id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN',
  priority INTEGER NOT NULL DEFAULT 3, due_at TEXT, est_pomodoros INTEGER NOT NULL DEFAULT 1,
  source_type TEXT NOT NULL DEFAULT 'chat', source_ref TEXT,
  carry_over_count INTEGER NOT NULL DEFAULT 0, planned_for TEXT, snoozed_until TEXT,
  content_hash TEXT NOT NULL, created_at TEXT NOT NULL, touched_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_focus_sessions (
  session_id TEXT PRIMARY KEY, task_id TEXT, workday_session_id TEXT NOT NULL,
  planned_minutes INTEGER NOT NULL, actual_minutes INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT, note TEXT NOT NULL DEFAULT '',
  real_started_at TEXT NOT NULL, real_ends_at TEXT NOT NULL, real_seconds INTEGER NOT NULL,
  compressed INTEGER NOT NULL DEFAULT 0, job_id TEXT);
CREATE TABLE IF NOT EXISTS ppa_memories (
  memory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, memory_type TEXT NOT NULL, content TEXT NOT NULL,
  content_hash TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT, last_used_at TEXT,
  use_count INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_ppa_memories_user ON ppa_memories(user_id, memory_type, status);
CREATE TABLE IF NOT EXISTS ppa_agent_sessions (
  session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',
  started_at TEXT NOT NULL, ended_at TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS ppa_scratch_files (
  session_id TEXT NOT NULL, path TEXT NOT NULL, is_dir INTEGER NOT NULL DEFAULT 0,
  content TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'note', meta TEXT NOT NULL DEFAULT '{}',
  promote_on_end INTEGER NOT NULL DEFAULT 0, promote_target TEXT NOT NULL DEFAULT 'memory',
  promotion_state TEXT NOT NULL DEFAULT 'N', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, path));
CREATE TABLE IF NOT EXISTS ppa_memory_promotion_queue (
  queue_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, path TEXT NOT NULL,
  target TEXT NOT NULL, chunk TEXT NOT NULL, content_hash TEXT NOT NULL,
  consumed TEXT NOT NULL DEFAULT 'N', outcome TEXT, outcome_ref TEXT,
  staged_at TEXT NOT NULL, consumed_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_action_audit (
  action_id TEXT PRIMARY KEY, run_id TEXT, thread_id TEXT NOT NULL, session_id TEXT NOT NULL,
  origin TEXT NOT NULL, tool_name TEXT NOT NULL, tier TEXT NOT NULL, summary TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL, risk TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL, delivery TEXT, result TEXT, undo_hint TEXT, decision_note TEXT,
  created_at TEXT NOT NULL, decided_at TEXT, executed_at TEXT, real_created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_notifications (
  notification_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}', job_id TEXT, run_id TEXT, created_at TEXT NOT NULL,
  real_created_at TEXT NOT NULL, read_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_automation_queue (
  job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, task_id TEXT, schedule_name TEXT,
  payload TEXT NOT NULL DEFAULT '{}', clock TEXT NOT NULL, fires_at TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'ARMED', dedupe_key TEXT UNIQUE, created_at TEXT NOT NULL,
  fired_at TEXT, finished_at TEXT, rearmed_at TEXT, notification_id TEXT, run_id TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS ppa_schedules (
  schedule_name TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, days TEXT NOT NULL,
  local_time TEXT NOT NULL, request TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  last_fired_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_skill_registry (
  skill_name TEXT PRIMARY KEY, description TEXT NOT NULL, triggers TEXT NOT NULL, body TEXT NOT NULL,
  body_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE', updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1, origin TEXT NOT NULL DEFAULT 'authored');
CREATE TABLE IF NOT EXISTS ppa_skill_versions (
  skill_name TEXT NOT NULL, version INTEGER NOT NULL, description TEXT NOT NULL, triggers TEXT NOT NULL,
  body TEXT NOT NULL, body_sha256 TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'authored',
  evidence TEXT NOT NULL DEFAULT '{}', drafted_by TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'CANDIDATE', gate TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  PRIMARY KEY (skill_name, version));
CREATE TABLE IF NOT EXISTS ppa_skill_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT, skill_name TEXT NOT NULL, version INTEGER,
  action TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_turns (
  turn_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'live',
  request TEXT NOT NULL, planned_by TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '[]',
  tools_bound TEXT NOT NULL DEFAULT '[]', context_layers TEXT NOT NULL DEFAULT '{}',
  tool_calls TEXT NOT NULL DEFAULT '[]', outcome TEXT, owner_words TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL, ended_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_model_calls (
  call_id INTEGER PRIMARY KEY AUTOINCREMENT, turn_id TEXT NOT NULL, step INTEGER NOT NULL,
  fresh_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
  seconds REAL NOT NULL DEFAULT 0, usd REAL NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_tool_registry (
  tool_name TEXT PRIMARY KEY, source TEXT NOT NULL, tier TEXT NOT NULL, exposed INTEGER NOT NULL,
  description TEXT NOT NULL, input_schema TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_agent_runs (
  run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, session_id TEXT NOT NULL, trigger TEXT NOT NULL,
  responder TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, answer TEXT,
  trace TEXT NOT NULL DEFAULT '{}', started_at TEXT NOT NULL, real_started_at TEXT NOT NULL,
  real_finished_at TEXT);
CREATE TABLE IF NOT EXISTS ppa_thread_messages (
  message_id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, session_id TEXT NOT NULL,
  run_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, responder TEXT, trigger TEXT,
  created_at TEXT NOT NULL, real_created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ppa_decision_log (
  decision_id TEXT PRIMARY KEY, kind TEXT NOT NULL, questions INTEGER NOT NULL DEFAULT 0,
  seconds REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL,
  summary TEXT, created_at TEXT NOT NULL, real_created_at TEXT NOT NULL);
"""

HARNESS_TABLES = tuple(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA))
# Columns added after a table first shipped. A store made by an earlier build gains them at start-up.
ADDED_COLUMNS = (("ppa_skill_registry", "version", "INTEGER NOT NULL DEFAULT 1"),
                 ("ppa_skill_registry", "origin", "TEXT NOT NULL DEFAULT 'authored'"))
CHECKPOINT_TABLES = ("checkpoints", "writes")
LOCAL_CHECKPOINTS = ("checkpoints", "writes")
ORACLE_CHECKPOINTS = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def oracle() -> bool:
    """Whether the harness tables live in Oracle AI Database."""
    return _state["kind"] == "oracle"


def _choose() -> str:
    """Decide the substrate once, at start-up."""
    wanted = os.environ.get("PPA_SUBSTRATE", "auto").strip().lower()
    if wanted in ("local", "sqlite"):
        return "local"
    if wanted == "oracle" or oracle_store.reachable(1.5):
        return "oracle"
    return "local"


def _use(kind: str, note: str = "") -> None:
    global SUBSTRATE, CHECKPOINT_TABLES
    _state.update(kind=kind, note=note)
    SUBSTRATE = oracle_store.LABEL if kind == "oracle" else "Local store"
    CHECKPOINT_TABLES = ORACLE_CHECKPOINTS if kind == "oracle" else LOCAL_CHECKPOINTS
_STATEMENT = re.compile(
    r"^\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|SELECT\b.*?\bFROM)\s+\"?(\w+)\"?",
    re.IGNORECASE | re.DOTALL)


def db_path() -> Path:
    """Harness state is kept per owner, so a practice run never mixes with a real account."""
    return DATA_DIR / f"ppa_{world.identity()}.sqlite"


def checkpoint_path() -> Path:
    """LangGraph checkpoints get their own file, so the async saver never waits on harness writes."""
    return DATA_DIR / f"ppa_{world.identity()}_checkpoints.sqlite"


def real_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def set_route(route: str | None) -> None:
    """Label the statements of the current request in the activity stream."""
    _route.value = route


def _trace(statement: str) -> None:
    match = _STATEMENT.match(statement)
    if not match:
        return
    table = match.group(1).lower()
    if table.startswith("sqlite_") or table == "ppa_meta":
        return
    operation = "READ" if statement.lstrip()[:6].upper() == "SELECT" else "WRITE"
    if operation == "WRITE":
        note_write(table)
    bus.publish("activity", table=table, operation=operation,
                route=getattr(_route, "value", None) or "harness")


def note_write(table: str) -> None:
    _writes[table] = _writes.get(table, 0) + 1


def write_counts() -> dict[str, int]:
    return dict(_writes)


@contextmanager
def quiet() -> Iterator[None]:
    """Reads made only to report status are not activity, and stay out of the activity stream."""
    token = _quiet.set(True)
    try:
        yield
    finally:
        _quiet.reset(token)


def connect(*, trace: bool = True, path: Path | None = None):
    if oracle():
        return oracle_store.connect(world.identity(), _trace if trace and not _quiet.get() else None)
    connection = sqlite3.connect(path or db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    if trace and not _quiet.get():
        connection.set_trace_callback(_trace)
    return connection


def rows(sql: str, params: Iterable[Any] = (), *, trace: bool = True) -> list[dict[str, Any]]:
    connection = connect(trace=trace)
    try:
        with connection:
            return [dict(item) for item in connection.execute(sql, tuple(params)).fetchall()]
    finally:
        connection.close()


def row(sql: str, params: Iterable[Any] = (), *, trace: bool = True) -> dict[str, Any] | None:
    found = rows(sql, params, trace=trace)
    return found[0] if found else None


def execute(sql: str, params: Iterable[Any] = (), *, trace: bool = True) -> int:
    connection = connect(trace=trace)
    try:
        with connection:
            return connection.execute(sql, tuple(params)).rowcount
    finally:
        connection.close()


def get_meta(key: str, default: str | None = None) -> str | None:
    found = row("SELECT value FROM ppa_meta WHERE key=?", (key,), trace=False)
    return found["value"] if found else default


def set_meta(key: str, value: str | None) -> None:
    if value is None:
        execute("DELETE FROM ppa_meta WHERE key=?", (key,), trace=False)
    else:
        execute("INSERT INTO ppa_meta(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value), trace=False)


def loads(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value else default


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _start_oracle() -> None:
    oracle_store.create_tables(world.identity(), SCHEMA)
    chosen = oracle_store.settings()
    _state.update(path=f"schema {oracle_store.schema_name(world.identity())} at {chosen['dsn']}")


def _start_local() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = connect(trace=False)
    with connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        for table, column, declared in ADDED_COLUMNS:
            present = {item["name"] for item in connection.execute(f'PRAGMA table_info("{table}")')}
            if column not in present:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declared}")
    connection.close()
    _state.update(path=str(db_path()))


def initialize() -> None:
    """Idempotent, additive warm-up. Existing state is never reset here."""
    with _lock:
        try:
            kind = _choose()
            _use(kind)
            if kind == "oracle":
                try:
                    _start_oracle()
                except Exception as exc:
                    if os.environ.get("PPA_SUBSTRATE", "auto").strip().lower() == "oracle":
                        raise
                    # Asked for nothing in particular, and Oracle could not be used: say why, carry on.
                    _use("local", f"Oracle AI Database could not be used: {str(exc).splitlines()[0][:200]}")
                    _start_local()
            else:
                _start_local()
            sync_contacts(world.contacts())
            _state.update(ready=True, error=None)
        except Exception as exc:
            _state.update(ready=False, error=str(exc))
            raise


def sync_contacts(contacts: list[dict[str, Any]]) -> int:
    """Mirror the gateway's derived contacts; VIP status is read, never invented."""
    stamp = real_now()
    connection = connect(trace=False)
    with connection:
        connection.execute("DELETE FROM ppa_contacts")
        for index, item in enumerate(contacts):
            connection.execute(
                "INSERT OR REPLACE INTO ppa_contacts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item["email"].lower(), item.get("contact_id") or f"C-{index + 1:03d}",
                 item.get("name") or item["email"], item.get("organisation") or "",
                 item.get("role") or "", item.get("relationship") or "", int(bool(item.get("is_vip"))),
                 item.get("vip_source") or "", int(item.get("messages_sent") or 0), stamp))
    connection.close()
    return len(contacts)


def contacts() -> list[dict[str, Any]]:
    found = rows("SELECT * FROM ppa_contacts ORDER BY is_vip DESC, messages_sent DESC, name")
    return [{**item, "is_vip": bool(item["is_vip"])} for item in found]


def _reset_oracle() -> None:
    present = set(oracle_store.tables(world.identity()))
    connection = connect(trace=False)
    try:
        with connection:
            for table in (*HARNESS_TABLES, *ORACLE_CHECKPOINTS):
                if table in present:
                    connection.execute(f"DELETE FROM {table}")
    finally:
        connection.close()


def reset() -> None:
    """Empty every harness table and the LangGraph checkpoints for this owner."""
    with _lock:
        if oracle():
            _reset_oracle()
            initialize()
            return
        for path, tables in ((db_path(), HARNESS_TABLES), (checkpoint_path(), CHECKPOINT_TABLES)):
            if not path.exists():
                continue
            connection = sqlite3.connect(path, timeout=30)
            with connection:
                present = {item[0] for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for table in tables:
                    if table in present:
                        connection.execute(f'DELETE FROM "{table}"')
            connection.close()
    initialize()


def counts() -> dict[str, int]:
    connection = connect(trace=False)
    try:
        return {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in HARNESS_TABLES}
    finally:
        connection.close()


def status() -> dict[str, Any]:
    if not _state["ready"]:
        return {"ready": False, "substrate": SUBSTRATE, "error": _state["error"]}
    if oracle():
        note = ("One schema for each workspace owner, beside the notebook's schema. The harness tables "
                "and LangGraph's checkpoints live in it.")
    else:
        note = _state["note"] or "One file for each workspace owner, used when no database answers."
    return {"ready": True, "substrate": SUBSTRATE, "kind": _state["kind"], "path": _state["path"],
            "tables": counts(), "note": note}
