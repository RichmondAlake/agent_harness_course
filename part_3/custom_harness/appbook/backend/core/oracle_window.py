"""A read-only window on the notebook's Oracle AI Database.

The appbook keeps its own state in SQLite. After a learner runs the
custom-harness notebook, this module shows what that harness left in Oracle AI
Database 26ai: tables, views, scheduler jobs and the embedding model.

It never writes. Every connection opens a read-only transaction, every
statement is a SELECT, identifiers are built only from names the data
dictionary returned, and values are bound. Nothing else in the appbook depends
on it: when the database cannot be reached, the window says so.
"""
from __future__ import annotations

import array
import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.config import settings

ROWS = 50               # the newest rows shown for one object
PREVIEW = 200           # characters of a long value shown in the grid, and read from a LOB
VECTOR_PREVIEW = 4      # numbers of a vector shown
CALL_MILLISECONDS = 8000        # the longest one statement may take
ANSWER_SECONDS = 9              # the longest the statements of one answer may take together
COUNT_MILLISECONDS = 1500       # the longest one row count may take
PROBE_MILLISECONDS = 2000       # the longest the reachability check may take
COUNTING_SECONDS = 6            # after this, the remaining objects are listed without a count
CATALOGUE_SECONDS = 5           # how long a catalogue is reused
PROBE_SECONDS = 15              # how long a reachability check is reused
NAMES_SECONDS = 60              # how long the list of names from the dictionary is reused
BUSY = "The database did not answer in time. It may be busy with the notebook. Try again in a moment."
HOW = "Run the custom-harness notebook, which starts the database."
LOBS = ("CLOB", "NCLOB", "BLOB")
# Dictionary views that describe time and models. Only the columns that exist are read.
DICTIONARY = {
    "USER_SCHEDULER_JOBS": ["JOB_NAME", "JOB_TYPE", "JOB_ACTION", "REPEAT_INTERVAL", "ENABLED", "STATE",
                            "RUN_COUNT", "FAILURE_COUNT", "LAST_START_DATE", "NEXT_RUN_DATE", "COMMENTS"],
    "USER_MINING_MODELS": ["MODEL_NAME", "MINING_FUNCTION", "ALGORITHM", "ALGORITHM_TYPE", "CREATION_DATE",
                           "BUILD_DURATION", "MODEL_SIZE", "COMMENTS"],
}
GROUPS = [
    ("Harness tables", "What the notebook's harness owns: tasks, focus sessions, the action log, registries."),
    ("Governed views", "One definition each, kept as a view, so every reader gets the same answer."),
    ("LangGraph checkpoints", "The state of the graph after every step, kept by OracleSaver."),
    ("Oracle Agent Memory", "Long-term and episodic memory, with the chunks that vector search reads."),
    ("Scheduler and model", "The jobs DBMS_SCHEDULER runs and the embedding model inside the database."),
    ("Maintained by the database", "Storage for the text index, the vector index and the model."),
]
TIME_WORDS = ("CREATED", "STARTED", "UPDATED", "FIRED", "DECIDED")

_cache: dict[str, tuple[float, Any]] = {}


class NotReachable(RuntimeError):
    """The database did not accept a connection."""


class UnknownObject(KeyError):
    """The name did not come from the data dictionary."""


class Busy(RuntimeError):
    """The database accepted the connection and did not answer within the time allowed."""


def quoted(name: str, known: set[str] | list[str]) -> str:
    """An identifier for a statement. Only a name the data dictionary returned is accepted."""
    if name not in known or '"' in name or "\x00" in name:
        raise UnknownObject(name)
    return f'"{name}"'


def _connect(milliseconds: int = CALL_MILLISECONDS) -> Any:
    import oracledb

    try:
        connection = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password,
                                      dsn=settings.oracle_dsn,
                                      tcp_connect_timeout=settings.oracle_connect_seconds)
    except Exception as exc:          # the driver raises several error classes for one fact
        raise NotReachable(str(exc).splitlines()[0][:200]) from exc
    connection.call_timeout = milliseconds
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
    except oracledb.Error as exc:
        connection.close()
        raise Busy(BUSY) from exc
    return connection


def _timed_out(exc: Exception) -> bool:
    return "DPY-4024" in str(exc) or "DPY-4011" in str(exc)


class Clock:
    """One answer has a fixed time to spend. Each statement gets what is left of it."""

    def __init__(self, connection: Any, seconds: float = ANSWER_SECONDS) -> None:
        self.connection, self.ends = connection, time.monotonic() + seconds

    def run(self, cursor: Any, statement: str, **binds: Any) -> Any:
        left = int((self.ends - time.monotonic()) * 1000)
        if left <= 0:
            raise Busy(BUSY)
        self.connection.call_timeout = min(CALL_MILLISECONDS, left)
        cursor.execute(statement, **binds)
        return cursor


def _remembered(key: str, seconds: float) -> Any:
    found = _cache.get(key)
    return found[1] if found and time.monotonic() - found[0] < seconds else None


def _remember(key: str, value: Any) -> Any:
    _cache[key] = (time.monotonic(), value)
    return value


def forget() -> None:
    _cache.clear()


def _memory_prefixes(names: list[str]) -> list[str]:
    """Oracle Agent Memory names its tables after its store: a prefix that owns a MEMORY and a THREAD table."""
    found = {name[: -len("_MEMORY")] for name in names if name.endswith("_MEMORY")}
    return sorted(prefix for prefix in found if f"{prefix}_THREAD" in names)


def group_of(name: str, kind: str, prefixes: list[str]) -> str:
    if name in DICTIONARY:
        return "Scheduler and model"
    if "$" in name:
        return "Maintained by the database"
    if name.startswith("PPA_V_") and kind == "view":
        return "Governed views"
    if name.startswith("PPA_"):
        return "Harness tables"
    if name.startswith("CHECKPOINT"):
        return "LangGraph checkpoints"
    if name == "AGENT_MEMORY_STORES" or any(name.startswith(prefix + "_") for prefix in prefixes):
        return "Oracle Agent Memory"
    return "Harness tables" if kind == "table" else "Governed views"


def _objects(cursor: Any, clock: Clock) -> dict[str, dict[str, Any]]:
    """Every table and view of this user, from the data dictionary."""
    clock.run(cursor, "SELECT table_name, 'table' FROM user_tables UNION ALL "
                      "SELECT view_name, 'view' FROM user_views")
    found = {name: {"name": name, "kind": kind} for name, kind in cursor.fetchall()}
    clock.run(cursor, "SELECT table_name, COUNT(*) FROM user_tab_columns GROUP BY table_name")
    for name, total in cursor.fetchall():
        if name in found:
            found[name]["columns"] = total
    for name, preferred in DICTIONARY.items():
        clock.run(cursor, "SELECT column_name FROM all_tab_columns WHERE owner = 'SYS' "
                          "AND table_name = :name", name=name)
        present = {row[0] for row in cursor.fetchall()}
        if present:
            found[name] = {"name": name, "kind": "dictionary view",
                           "columns": len([item for item in preferred if item in present])}
    prefixes = _memory_prefixes(list(found))
    for item in found.values():
        item["group"] = group_of(item["name"], item["kind"], prefixes)
    return _remember("objects", found)


def _count(cursor: Any, name: str, known: set[str]) -> int | None:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {quoted(name, known)}")
        return cursor.fetchone()[0]
    except UnknownObject:
        raise
    except Exception:                 # an object that cannot be read is listed without a count
        return None


def _counts(objects: dict[str, dict[str, Any]]) -> None:
    """A row count for each object, within a fixed time. What is left over is listed without one."""
    known, started, connection = set(objects), time.monotonic(), None
    try:
        for item in objects.values():
            item["rows"] = None
            if time.monotonic() - started > COUNTING_SECONDS:
                continue
            if connection is None or not connection.is_healthy():
                connection = _connect(COUNT_MILLISECONDS)
            with connection.cursor() as cursor:
                item["rows"] = _count(cursor, item["name"], known)
    except (NotReachable, Busy):
        pass
    finally:
        if connection is not None:
            connection.close()


def catalogue() -> dict[str, Any]:
    """What exists, grouped, with a row count for each object. Discovered, never assumed."""
    found = _remembered("catalogue", CATALOGUE_SECONDS)
    if found is not None:
        return found
    import oracledb

    connection = _connect()
    clock = Clock(connection)
    try:
        with connection.cursor() as cursor:
            objects = _objects(cursor, clock)
            jobs = clock.run(cursor, "SELECT COUNT(*) FROM user_scheduler_jobs").fetchone()[0]
            clock.run(cursor, "SELECT model_name, algorithm, mining_function FROM user_mining_models "
                              "ORDER BY model_name")
            models = [{"name": name, "algorithm": algorithm, "function": function}
                      for name, algorithm, function in cursor.fetchall()]
        version = connection.version
    except oracledb.Error as exc:
        raise Busy(BUSY if _timed_out(exc) else str(exc).splitlines()[0][:200]) from exc
    finally:
        connection.close()
    _counts(objects)
    groups = [{"name": name, "about": about,
               "objects": sorted((item for item in objects.values() if item["group"] == name),
                                 key=lambda item: item["name"])}
              for name, about in GROUPS]
    tables = sum(item["kind"] == "table" for item in objects.values())
    _remember("probe", {"reachable": True, "tables": tables, "version": version})
    return _remember("catalogue", {
        "reachable": True, "version": version, "tables": tables,
        "views": sum(item["kind"] == "view" for item in objects.values()),
        "rows": sum(item["rows"] or 0 for item in objects.values() if item["kind"] == "table"),
        "uncounted": sum(item["rows"] is None for item in objects.values()),
        "scheduler_jobs": jobs, "models": models,
        "groups": [group for group in groups if group["objects"]]})


def probe() -> dict[str, Any]:
    """Can the database be reached, and how many tables does this user have. Reused for a few seconds."""
    found = _remembered("probe", PROBE_SECONDS)
    if found is not None:
        return found
    import oracledb

    try:
        connection = _connect(PROBE_MILLISECONDS)
    except NotReachable as exc:
        return _remember("probe", {"reachable": False, "detail": str(exc)})
    except Busy:
        return _remember("probe", {"reachable": True, "tables": None, "version": None})
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM user_tables")
            tables = cursor.fetchone()[0]
        return _remember("probe", {"reachable": True, "tables": tables, "version": connection.version})
    except oracledb.Error:
        return _remember("probe", {"reachable": True, "tables": None, "version": None})
    finally:
        connection.close()


def _columns(cursor: Any, clock: Clock, name: str) -> list[dict[str, Any]]:
    if name in DICTIONARY:
        clock.run(cursor, "SELECT column_name, data_type, nullable FROM all_tab_columns "
                          "WHERE owner = 'SYS' AND table_name = :name ORDER BY column_id", name=name)
        return [{"name": column, "type": kind, "nullable": nullable == "Y"}
                for column, kind, nullable in cursor.fetchall() if column in DICTIONARY[name]]
    clock.run(cursor, "SELECT column_name, data_type, nullable FROM user_tab_columns "
                      "WHERE table_name = :name ORDER BY column_id", name=name)
    return [{"name": column, "type": kind, "nullable": nullable == "Y"}
            for column, kind, nullable in cursor.fetchall()]


def newest_by(columns: list[dict[str, Any]]) -> str | None:
    """The column that says which rows are newest: a time column, or a checkpoint id."""
    timed = [item["name"] for item in columns
             if item["type"] == "DATE" or item["type"].startswith("TIMESTAMP")]
    for word in TIME_WORDS:
        for name in timed:
            if word in name:
                return name
    if timed:
        return timed[0]
    names = [item["name"] for item in columns]
    return "CHECKPOINT_ID" if "CHECKPOINT_ID" in names else None


def _text(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8"), "text"
    except UnicodeDecodeError:
        return raw.hex(), "hexadecimal"


def shape(value: Any, kind: str, length: int | None = None) -> Any:
    """One value, in a form that can be sent to the page. Long values are cut and say so."""
    if value is None and length is None:
        return None
    if kind in LOBS:
        if isinstance(value, bytes):
            first, encoding = _text(value)
        else:
            first, encoding = value or "", "text"
        unit = "bytes" if kind == "BLOB" else "characters"
        return {"kind": kind.lower(), "length": length or 0, "unit": unit, "first": first,
                "encoding": encoding, "truncated": (length or 0) > PREVIEW}
    if isinstance(value, array.array):
        return {"kind": "vector", "dimension": len(value), "format": value.typecode,
                "first": [round(float(number), 6) for number in value[:VECTOR_PREVIEW]]}
    if isinstance(value, (dict, list)):
        return {"kind": "json", "value": json.loads(json.dumps(value, default=str))}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, bytes):
        return {"kind": "raw", "length": len(value), "unit": "bytes", "first": value[:PREVIEW].hex(),
                "encoding": "hexadecimal", "truncated": len(value) > PREVIEW}
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def read(name: str, limit: int = ROWS) -> dict[str, Any]:
    """Columns, row count and the newest rows of one object."""
    limit = min(max(limit, 1), ROWS)
    connection = _connect()
    clock = Clock(connection)
    try:
        with connection.cursor() as cursor:
            objects = _remembered("objects", NAMES_SECONDS) or _objects(cursor, clock)
            if name not in objects:
                raise UnknownObject(name)
            known = set(objects)
            columns = _columns(cursor, clock, name)
            names = [item["name"] for item in columns]
            selected = []
            for item in columns:
                column = quoted(item["name"], names)
                if item["type"] in LOBS:
                    # A LOB is never fetched whole: its length and its first characters are enough.
                    selected += [f"DBMS_LOB.GETLENGTH({column})", f"DBMS_LOB.SUBSTR({column}, {PREVIEW}, 1)"]
                elif item["type"].endswith("WITH TIME ZONE"):
                    # The thin driver cannot read a named time zone, so the database writes it out.
                    selected.append(f"TO_CHAR({column}, 'YYYY-MM-DD\"T\"HH24:MI:SS TZR')")
                else:
                    selected.append(column)
            ordered = newest_by(columns)
            order = f" ORDER BY {quoted(ordered, names)} DESC NULLS LAST" if ordered else ""
            clock.run(cursor, f"SELECT {', '.join(selected)} FROM {quoted(name, known)}{order} "
                              "FETCH FIRST :limit ROWS ONLY", limit=limit)
            fetched = cursor.fetchall()
            total = clock.run(cursor, f"SELECT COUNT(*) FROM {quoted(name, known)}").fetchone()[0]
    finally:
        connection.close()
    rows = []
    for record in fetched:
        values, position = {}, 0
        for item in columns:
            if item["type"] in LOBS:
                values[item["name"]] = shape(record[position + 1], item["type"], record[position])
                position += 2
            else:
                values[item["name"]] = shape(record[position], item["type"])
                position += 1
        rows.append(values)
    return {"reachable": True, "name": name, "kind": objects[name]["kind"], "group": objects[name]["group"],
            "row_count": total, "columns": columns, "ordered_by": ordered, "limit": limit, "rows": rows,
            "access": "read-only"}


def status() -> dict[str, Any]:
    """Where the window looks. The password is never part of any answer."""
    return {"dsn": settings.oracle_dsn, "user": settings.oracle_user, "driver": "python-oracledb, thin mode",
            "access": "read-only: every transaction is opened read-only and every statement is a SELECT",
            "how": HOW}
