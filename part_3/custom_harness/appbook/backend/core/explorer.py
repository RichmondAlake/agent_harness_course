"""A read-only explorer over the tables the harness owns.

The table list is a fixed allowlist, not whatever the database happens to
hold. Identifiers come from that list and from each table's own columns;
values are always bound. There is no query text from the browser. Connection
secrets live in the gateway's own file and are not a table, so they cannot
appear here.
"""
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.core import store

MAX_ROWS = 100          # the most rows one page may return
EXPORT_ROWS = 500       # the most rows one export may return
PREVIEW = 160           # characters of a long cell shown in the grid
BINARY_BYTES = 4096     # bytes of a binary cell returned when it cannot be decoded

TABLES: dict[str, dict[str, str]] = {
    "ppa_tasks": {"group": "Tasks and focus", "about": "The running to-do list and its source links."},
    "ppa_focus_sessions": {"group": "Tasks and focus", "about": "Every Pomodoro: planned, actual, status."},
    "ppa_automation_queue": {"group": "Timers and routines",
                             "about": "Every focus timer and scheduled job, armed or fired."},
    "ppa_schedules": {"group": "Timers and routines", "about": "The routines and when they run."},
    "ppa_notifications": {"group": "Timers and routines", "about": "What timers and routines reported."},
    "ppa_action_audit": {"group": "Approvals", "about": "What was done, why, and what was delivered."},
    "ppa_memories": {"group": "Memory", "about": "Preferences, people, commitments, facts and episodes."},
    "ppa_memory_promotion_queue": {"group": "Memory", "about": "Notes staged for promotion, by content hash."},
    "ppa_agent_sessions": {"group": "Workday scratch pad", "about": "One row per workday session."},
    "ppa_scratch_files": {"group": "Workday scratch pad", "about": "Captures, the day plan and working notes."},
    "ppa_contacts": {"group": "People", "about": "Contacts and derived VIP flags from the gateway."},
    "ppa_agent_runs": {"group": "The loop", "about": "Every run, typed or proactive, with its trace."},
    "ppa_thread_messages": {"group": "The loop", "about": "The readable transcript of each conversation."},
    "checkpoints": {"group": "The loop", "about": "LangGraph checkpoints, one per super-step.",
                    "database": "checkpoints"},
    "writes": {"group": "The loop", "about": "Pending writes LangGraph stores beside a checkpoint.",
               "database": "checkpoints"},
    "ppa_skill_registry": {"group": "Registries", "about": "The live skills, each with a version pointer."},
    "ppa_skill_versions": {"group": "Registries", "about": "Every version of every skill, with its gate result."},
    "ppa_skill_log": {"group": "Registries", "about": "Every move of a live pointer: activate, retire, trial."},
    "ppa_turns": {"group": "The loop", "about": "The trajectory of each turn: request, tools, outcome."},
    "ppa_model_calls": {"group": "The loop", "about": "One row per model call: tokens by kind, seconds, cost."},
    "ppa_tool_registry": {"group": "Registries", "about": "Every tool, reachable or not, with its tier."},
    "ppa_decision_log": {"group": "Approvals", "about": "Every question put to System One: kind, time, tokens."},
    "ppa_meta": {"group": "Harness", "about": "Small settings: clock pin, watermark, switches."},
}


class UnknownTable(KeyError):
    """The name is not on the explorer's allowlist."""


def _path(table: str) -> Path:
    if table not in TABLES:
        raise UnknownTable(table)
    return store.checkpoint_path() if TABLES[table].get("database") == "checkpoints" else store.db_path()


# LangGraph's Oracle saver lays its checkpoints out in three tables, its local saver in two.
ON_ORACLE = {
    "checkpoint_blobs": {"group": "The loop", "about": "The values of each channel, stored once per version.",
                         "database": "checkpoints"},
    "checkpoint_writes": {"group": "The loop", "about": "Pending writes LangGraph stores beside a checkpoint.",
                          "database": "checkpoints"},
}


def listed() -> dict[str, dict[str, str]]:
    """The tables this explorer shows, under the names the database knows them by."""
    if not store.oracle():
        return TABLES
    found = {}
    for name, facts in TABLES.items():
        if name == "writes":
            found.update(ON_ORACLE)
        else:
            found[name] = facts
    return found


def stored(table: str) -> str:
    """The name a table has on this substrate. Only LangGraph's table of writes differs."""
    return "checkpoint_writes" if store.oracle() and table == "writes" else table


def _stored(table: str) -> str:
    return table


def _connect(table: str):
    if store.oracle():
        if table not in listed():
            raise UnknownTable(table)
        return store.connect(trace=False)
    path = _path(table)
    if not path.exists():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [{"name": item[1], "type": item[2] or "ANY", "primary_key": bool(item[5])}
            for item in connection.execute(f'PRAGMA table_info("{_stored(table)}")')]


def _kind(value: Any) -> str:
    if isinstance(value, bytes):
        return "binary"
    if isinstance(value, str) and value[:1] in "{[":
        try:
            json.loads(value)
            return "json"
        except ValueError:
            return "text"
    return "text" if isinstance(value, str) else "number"


def _cell(value: Any) -> Any:
    """A grid cell: short values as they are, long or binary ones as a preview."""
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, bytes):
        return {"kind": "binary", "length": len(value), "truncated": True,
                "preview": f"{len(value)} bytes"}
    if len(value) <= PREVIEW and _kind(value) == "text":
        return value
    return {"kind": _kind(value), "length": len(value), "truncated": len(value) > PREVIEW,
            "preview": " ".join(value[:PREVIEW].split())}


def _decode(table: str, column: str, value: bytes, row: sqlite3.Row) -> dict[str, Any]:
    """A binary value in full. LangGraph blobs are decoded so their content can be read."""
    try:
        if column == "metadata":
            return {"kind": "json", "length": len(value), "value": json.loads(value)}
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        decoded = JsonPlusSerializer().loads_typed((row["type"], value))
        return {"kind": "json", "length": len(value), "decoded_from": f"{row['type']} blob",
                "value": json.loads(json.dumps(decoded, default=repr))}
    except Exception:          # an unreadable blob is still shown, as bytes
        return {"kind": "binary", "length": len(value), "truncated": len(value) > BINARY_BYTES,
                "value": base64.b64encode(value[:BINARY_BYTES]).decode("ascii"), "encoding": "base64"}


def _full(table: str, row: sqlite3.Row) -> dict[str, Any]:
    shown = {}
    for column in row.keys():
        value = row[column]
        if isinstance(value, bytes):
            shown[column] = _decode(table, column, value, row)
        elif isinstance(value, str) and _kind(value) == "json":
            shown[column] = {"kind": "json", "length": len(value), "value": json.loads(value)}
        elif isinstance(value, str) and len(value) > PREVIEW:
            shown[column] = {"kind": "text", "length": len(value), "value": value}
        else:
            shown[column] = value
    return shown


def tables() -> list[dict[str, Any]]:
    """Every allowlisted table with its group, columns, row count and writes since start-up."""
    writes = store.write_counts()
    listed = []
    for name, facts in globals()["listed"]().items():
        connection = _connect(name)
        columns, count = [], 0
        if connection is not None:
            try:
                columns = _columns(connection, name)
                if columns:
                    count = connection.execute(f'SELECT COUNT(*) FROM "{_stored(name)}"').fetchone()[0]
            finally:
                connection.close()
        listed.append({"name": name, "group": facts["group"], "about": facts["about"],
                       "database": facts.get("database", "harness"), "columns": columns,
                       "row_count": count, "writes": writes.get(name, 0)})
    return listed


def page(table: str, *, limit: int = 25, offset: int = 0, sort: str | None = None,
         direction: str = "desc", search: str = "") -> dict[str, Any]:
    """One page of rows, newest first unless a column is chosen."""
    connection = _connect(table)
    limit = min(max(limit, 1), MAX_ROWS)
    if connection is None:
        return {"table": table, "columns": [], "rows": [], "total": 0, "matched": 0, "limit": limit,
                "offset": offset, "sort": "rowid", "direction": direction, "search": search}
    try:
        columns = _columns(connection, table)
        names = [item["name"] for item in columns]
        if sort is not None and sort not in names:
            raise ValueError(f"{sort} is not a column of {table}")
        order = f'"{sort}"' if sort else "rowid"
        order += " DESC" if direction == "desc" else " ASC"
        where, values = "", []
        if search.strip():
            searched = [item["name"] for item in columns if item["type"].upper() in ("TEXT", "")]
            where = "WHERE " + " OR ".join(f'"{name}" LIKE ? ESCAPE \'\\\'' for name in searched)
            term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values = [f"%{term}%"] * len(searched)
        stored = _stored(table)
        total = connection.execute(f'SELECT COUNT(*) FROM "{stored}"').fetchone()[0]
        matched = connection.execute(f'SELECT COUNT(*) FROM "{stored}" {where}', values).fetchone()[0]
        found = connection.execute(
            f'SELECT rowid AS _rowid, * FROM "{stored}" {where} ORDER BY {order} LIMIT ? OFFSET ?',
            (*values, limit, offset)).fetchall()
    finally:
        connection.close()
    return {"table": table, "columns": columns, "total": total, "matched": matched, "limit": limit,
            "offset": offset, "sort": sort or "rowid", "direction": direction, "search": search.strip(),
            "rows": [{"rowid": item["_rowid"], "cells": {name: _cell(item[name]) for name in names}}
                     for item in found]}


def record(table: str, rowid: int) -> dict[str, Any] | None:
    """One row with every value in full."""
    connection = _connect(table)
    if connection is None:
        return None
    try:
        found = connection.execute(f'SELECT * FROM "{_stored(table)}" WHERE rowid=?', (rowid,)).fetchone()
        return {"table": table, "rowid": rowid, "values": _full(table, found)} if found else None
    finally:
        connection.close()


def export(table: str) -> dict[str, Any]:
    """The newest rows of one table in full, for a learner to keep."""
    connection = _connect(table)
    if connection is None:
        return {"table": table, "rows": [], "limit": EXPORT_ROWS}
    try:
        found = connection.execute(f'SELECT * FROM "{_stored(table)}" ORDER BY rowid DESC LIMIT ?',
                                   (EXPORT_ROWS,)).fetchall()
        return {"table": table, "limit": EXPORT_ROWS, "rows": [_full(table, item) for item in found]}
    finally:
        connection.close()
