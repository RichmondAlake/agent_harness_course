"""Oracle AI Database as the appbook's substrate.

The appbook keeps its state through four functions in ``store``: ``rows``,
``row``, ``execute`` and ``connect``. Every module writes plain SQL against
them. This module runs that SQL on Oracle AI Database.

It does three jobs.

* **Schema.** It creates the harness tables in the appbook's own schema, beside
  the notebook's schema and never inside it. Each owner gets a schema, so a
  practice run never mixes with a real account.
* **Dialect.** It rewrites the few statements that Oracle spells differently:
  an upsert, ``LIMIT``, the order of insertion.
* **Rows.** It returns rows that behave the way the callers expect: names in
  lower case, and an empty string where a text column was declared ``NOT NULL``.
  Oracle stores an empty string as ``NULL``, and the callers must not notice.

Nothing here is an object-relational mapper. A statement goes to the database
as written unless one of the rules below applies, and each rule is a few lines
that can be read.
"""
from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Iterable, Iterator
from typing import Any, Callable

import oracledb

oracledb.defaults.fetch_lobs = False          # a CLOB comes back as text, not as a locator

LABEL = "Oracle AI Database"
KEY_LENGTH = 400
# Text that can grow past 4,000 bytes is stored as a CLOB. Everything else is VARCHAR2,
# because a CLOB cannot be a key, cannot be sorted and cannot be compared with "=".
LONG_TEXT = {"content", "body", "payload", "trace", "answer", "request", "result", "metadata", "meta",
             "input_schema", "summary", "chunk", "description", "triggers", "error", "decision_note",
             "undo_hint", "risk", "value", "context_layers", "tool_calls", "tools_bound", "evidence",
             "gate", "owner_words"}
ALREADY_EXISTS = ("ORA-00955", "ORA-01408", "ORA-01920", "ORA-01543", "ORA-02260", "ORA-02261")
GRANTS = ("CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "CREATE SEQUENCE", "CREATE PROCEDURE")

_pools: dict[str, oracledb.ConnectionPool] = {}
_lock = threading.RLock()
_tables: dict[str, dict[str, Any]] = {}       # table name -> what the portable schema says about it
_plans: dict[str, list[dict[str, Any]]] = {}  # statement -> the Oracle statements that carry it out


# ── Settings ──────────────────────────────────────────────────────────────────

def settings() -> dict[str, str]:
    """Where the database is. Each value can be set in the environment."""
    return {
        "dsn": os.environ.get("PPA_APPBOOK_ORA_DSN") or "127.0.0.1:1524/FREEPDB1",
        "prefix": os.environ.get("PPA_APPBOOK_ORA_USER") or "PPA3_APP",
        "password": os.environ.get("PPA_APPBOOK_ORA_PWD") or "PpaAppbook_2026!",
        "admin_password": os.environ.get("ORACLE_ADMIN_PASSWORD", ""),
        "tablespace": os.environ.get("PPA_APPBOOK_ORA_TABLESPACE", ""),
    }


def schema_name(identity: str) -> str:
    """One schema for each owner, named after the owner's identity."""
    return f"{settings()['prefix']}_{re.sub(r'[^A-Za-z0-9]', '', identity)[:12]}".upper()


def reachable(timeout: float = 3.0) -> bool:
    """Whether something answers at the database address. It does not prove a login."""
    import socket
    host, _, rest = settings()["dsn"].partition(":")
    try:
        with socket.create_connection((host, int(rest.split("/")[0] or 1521)), timeout=timeout):
            return True
    except OSError:
        return False


# ── The portable schema ───────────────────────────────────────────────────────

def _split(text: str, separator: str = ",") -> list[str]:
    """Split on a separator that is not inside brackets or quotes."""
    parts, depth, quote, current = [], 0, "", []
    for character in text:
        if quote:
            quote = "" if character == quote else quote
        elif character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    return parts + ["".join(current).strip()] if "".join(current).strip() else parts


def read_schema(script: str) -> dict[str, dict[str, Any]]:
    """Learn the tables from the appbook's ``CREATE TABLE`` script."""
    _tables.clear()
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\);", script, re.S):
        columns, keys = [], []
        for part in _split(" ".join(body.split())):
            composite = re.match(r"PRIMARY KEY\s*\((.*?)\)", part, re.I)
            if composite:
                keys = [item.strip() for item in composite.group(1).split(",")]
                continue
            column, kind, rest = re.match(r"(\w+)\s+(\w+)\s*(.*)", part).groups()
            default = re.search(r"DEFAULT\s+('(?:[^']*)'|\S+)", rest, re.I)
            columns.append({
                "name": column.lower(), "text": kind.upper() == "TEXT",
                "required": bool(re.search(r"NOT NULL", rest, re.I)),
                "key": bool(re.search(r"PRIMARY KEY", rest, re.I)),
                "unique": bool(re.search(r"\bUNIQUE\b", rest, re.I)),
                "counter": bool(re.search(r"AUTOINCREMENT", rest, re.I)),
                "default": default.group(1) if default else None})
            if columns[-1]["key"]:
                keys = [column.lower()]
        counter = next((item["name"] for item in columns if item["counter"]), None)
        _tables[name.lower()] = {
            "columns": columns, "keys": [key.lower() for key in keys],
            # The column that records the order of insertion. A table with its own
            # counter uses it, because Oracle allows one identity column in a table.
            "order": counter or "seq",
            "blank": {item["name"] for item in columns if item["text"] and item["required"]}}
    return _tables


def _column(table: str, item: dict[str, Any]) -> str:
    keyed = item["name"] in _tables[table]["keys"] or item["unique"]
    if item["counter"]:
        return f"{item['name']} NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY"
    if not item["text"]:
        kind = "NUMBER"
    elif item["name"] in LONG_TEXT and not keyed:
        kind = "CLOB"
    else:
        kind = f"VARCHAR2({KEY_LENGTH if keyed else 4000})"
    default = item["default"]
    clause = f" DEFAULT {default}" if default not in (None, "''") else ""
    # An empty string is NULL in Oracle, so a text column cannot be both required and empty.
    required = " NOT NULL" if item["required"] and not item["text"] else ""
    return f"{quoted(item['name'])} {kind}{clause}{required}{' UNIQUE' if item['unique'] else ''}"


def table_ddl(table: str) -> str:
    about = _tables[table]
    lines = [_column(table, item) for item in about["columns"]]
    # The order of insertion, which the portable SQL calls "rowid". Invisible, so that
    # SELECT * and INSERT without a column list see the table as it was declared.
    if about["order"] == "seq":
        lines.append("seq NUMBER INVISIBLE GENERATED ALWAYS AS IDENTITY")
    if about["keys"]:
        lines.append(f"PRIMARY KEY ({', '.join(quoted(key) for key in about['keys'])})")
    return f"CREATE TABLE {table} (\n  " + ",\n  ".join(lines) + ")"


RESERVED = {"trigger"}


def quoted(name: str) -> str:
    """A column whose name is an Oracle reserved word has to be written in quotes."""
    return f'"{name.upper()}"' if name.lower() in RESERVED else name


# ── Dialect ───────────────────────────────────────────────────────────────────

REWRITES: dict[str, str] = {
    # SQLite lets a query select columns that are neither grouped nor aggregated. Oracle asks
    # for a rule, so each one takes its value from the newest run of the thread.
    "SELECT thread_id, session_id, trigger, responder, COUNT(*) AS runs, "
    "MAX(real_started_at) AS last_active, SUM(status='awaiting_approval') AS waiting "
    "FROM ppa_agent_runs GROUP BY thread_id ORDER BY last_active DESC LIMIT ?":
        "SELECT thread_id, MAX(session_id) KEEP (DENSE_RANK LAST ORDER BY seq) AS session_id, "
        'MAX("TRIGGER") KEEP (DENSE_RANK LAST ORDER BY seq) AS "TRIGGER", '
        "MAX(responder) KEEP (DENSE_RANK LAST ORDER BY seq) AS responder, COUNT(*) AS runs, "
        "MAX(real_started_at) AS last_active, "
        "SUM(CASE WHEN status='awaiting_approval' THEN 1 ELSE 0 END) AS waiting "
        "FROM ppa_agent_runs GROUP BY thread_id ORDER BY last_active DESC LIMIT ?",
}
_PLACEHOLDER = re.compile(r"\?")
_LIMIT = re.compile(r"\s+LIMIT\s+(:p\d+|\d+)(?:\s+OFFSET\s+(:p\d+|\d+))?\s*$", re.I)
_INSERT = re.compile(r"^\s*INSERT(?:\s+OR\s+(REPLACE|IGNORE))?\s+INTO\s+\"?(\w+)\"?\s*", re.I)
_CONFLICT = re.compile(r"\s*ON\s+CONFLICT\s*\((.*?)\)\s*DO\s+(NOTHING|UPDATE\s+SET\s+(.*))\s*$", re.I | re.S)
_EMPTY = re.compile(r"(:p\d+)\s*=\s*''")


def _outside_quotes(sql: str, change: Callable[[str], str]) -> str:
    """Apply a change to the parts of a statement that are not inside a string literal."""
    pieces = re.split(r"('(?:[^']|'')*')", sql)
    return "".join(piece if index % 2 else change(piece) for index, piece in enumerate(pieces))


def _common(sql: str) -> str:
    """The rules that apply to every statement."""
    named = re.search(r"\b(?:FROM|INTO|UPDATE)\s+\"?(\w+)\"?", sql, re.I)
    order = _tables.get(named.group(1).lower(), {}).get("order", "seq") if named else "seq"
    counter = iter(range(1, 1000))
    sql = _outside_quotes(sql, lambda piece: _PLACEHOLDER.sub(lambda _: f":p{next(counter)}", piece))
    sql = _outside_quotes(sql, lambda piece: re.sub(r'"(\w+)"', r"\1", piece))
    sql = _outside_quotes(sql, lambda piece: re.sub(r"\btrigger\b", '"TRIGGER"', piece, flags=re.I))
    sql = _outside_quotes(sql, lambda piece: re.sub(r"\browid\b", order, piece, flags=re.I))
    sql = _EMPTY.sub(r"\1 IS NULL", sql)       # a parameter compared with '' means "is it empty?"
    sql = re.sub(rf"\b{order}\s+AS\s+_rowid\b\s*,\s*\*", f'{order} AS "_rowid", t.*', sql, flags=re.I)
    if '"_rowid"' in sql:
        sql = re.sub(r"\bFROM\s+(\w+)", r"FROM \1 t", sql, count=1, flags=re.I)
    limit = _LIMIT.search(sql)
    if limit:
        first, skip = limit.group(1), limit.group(2)
        window = f" OFFSET {skip} ROWS FETCH NEXT {first} ROWS ONLY" if skip else f" FETCH FIRST {first} ROWS ONLY"
        sql = sql[:limit.start()] + window
    return sql.strip().rstrip(";")


def _insert(sql: str) -> list[dict[str, Any]] | None:
    """Turn the three kinds of upsert into statements Oracle runs one after another."""
    head = _INSERT.match(sql)
    if not head:
        return None
    mode, table = (head.group(1) or "").upper(), head.group(2).lower()
    rest = sql[head.end():]
    names = None
    if rest.startswith("("):
        close = rest.index(")")
        names, rest = [item.strip().strip('"').lower() for item in rest[1:close].split(",")], rest[close + 1:]
    values_at = re.match(r"\s*VALUES\s*\(", rest, re.I)
    if not values_at:
        return None
    depth, end = 1, values_at.end()
    while depth:                                   # find the bracket that closes VALUES (
        depth += {"(": 1, ")": -1}.get(rest[end], 0)
        end += 1
    values, tail = _split(rest[values_at.end():end - 1]), rest[end:]
    names = names or [item["name"] for item in _tables[table]["columns"]]
    given = dict(zip(names, values))
    columns = ", ".join(quoted(name) for name in names)
    plain = {"sql": f"INSERT INTO {table} ({columns}) VALUES ({', '.join(values)})"}
    conflict = _CONFLICT.match(tail)
    if not mode and not conflict:
        return [plain]
    where = lambda keys: " AND ".join(f"{quoted(key)} = {given[key]}" for key in keys)
    if mode == "REPLACE":
        return [{"sql": f"DELETE FROM {table} WHERE {where(_tables[table]['keys'])}"}, plain]
    if mode == "IGNORE" or conflict.group(2).upper() == "NOTHING":
        return [{**plain, "ignore_duplicate": True}]
    keys = [item.strip().strip('"').lower() for item in conflict.group(1).split(",")]
    changes = re.sub(r"\bexcluded\.(\w+)", lambda found: given[found.group(1).lower()], conflict.group(3))
    return [{"sql": f"UPDATE {table} SET {changes} WHERE {where(keys)}", "stop_if_changed": True},
            {**plain, "ignore_duplicate": True, "counts": True}]


def plan(sql: str) -> list[dict[str, Any]]:
    """The Oracle statements that carry out one statement of the appbook."""
    wanted = " ".join(sql.split())
    if wanted not in _plans:
        text = _common(REWRITES.get(wanted, wanted))
        steps = _insert(text) or [{"sql": text}]
        table = re.search(r"\b(?:FROM|INTO|UPDATE)\s+(\w+)", text, re.I)
        for step in steps:
            step["binds"] = sorted(set(re.findall(r":p(\d+)", _outside_quotes(step["sql"], str))), key=int)
            step["table"] = table.group(1).lower() if table else ""
        _plans[wanted] = steps
    return _plans[wanted]


# ── Rows ──────────────────────────────────────────────────────────────────────

class Row(dict):
    """A row that answers to a column name and to a position, as the callers expect."""

    def __getitem__(self, key: Any) -> Any:
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

    def keys(self):                                # noqa: D102  (same contract as sqlite3.Row)
        return list(super().keys())


class Result:
    """What ``execute`` gives back: the rows, and how many rows a change touched."""

    def __init__(self, rows: list[Row], rowcount: int, description: list[str]) -> None:
        self._rows, self.rowcount, self.description = rows, rowcount, [(name,) for name in description]

    def fetchall(self) -> list[Row]:
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self) -> Row | None:
        return self._rows.pop(0) if self._rows else None

    def __iter__(self) -> Iterator[Row]:
        return iter(self.fetchall())


def _value(value: Any) -> Any:
    return int(value) if isinstance(value, bool) else value


def _number(value: Any) -> Any:
    """A value as the callers expect it: whole numbers as integers, JSON as its text."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return int(value) if isinstance(value, float) and value.is_integer() else value


class Connection:
    """The part of a database connection that the appbook uses."""

    def __init__(self, pool: oracledb.ConnectionPool, trace: Callable[[str], None] | None = None) -> None:
        self._pool, self._trace = pool, trace
        self._raw = pool.acquire()

    def set_trace_callback(self, trace: Callable[[str], None] | None) -> None:
        self._trace = trace

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> Result:
        if sql.lstrip().upper().startswith("PRAGMA"):
            return self._pragma(sql)
        if self._trace:
            self._trace(sql)
        given = {str(index): _value(value) for index, value in enumerate(tuple(parameters), 1)}
        touched, rows, names = 0, [], []
        with self._raw.cursor() as cursor:
            for step in plan(sql):
                binds = {f"p{index}": given[index] for index in step["binds"]}
                try:
                    cursor.execute(step["sql"], binds)
                except oracledb.IntegrityError:
                    if not step.get("ignore_duplicate"):
                        raise
                    continue
                touched = cursor.rowcount
                if step.get("stop_if_changed") and touched:
                    break
                if cursor.description:
                    names = [column[0].lower() for column in cursor.description]
                    blank = _tables.get(step["table"], {}).get("blank", set())
                    rows = [Row({name: ("" if value is None and name in blank else _number(value))
                                 for name, value in zip(names, record)}) for record in cursor.fetchall()]
        return Result(rows, touched, names)

    def _pragma(self, sql: str) -> Result:
        """``PRAGMA table_info``: the columns of a table, in the shape SQLite gives them."""
        asked = re.search(r'table_info\("?(\w+)"?\)', sql)
        if not asked:
            return Result([], 0, [])
        with self._raw.cursor() as cursor:
            cursor.execute("""SELECT column_id - 1, LOWER(column_name), data_type, nullable
                FROM user_tab_columns WHERE table_name = :name AND column_id IS NOT NULL
                ORDER BY column_id""", {"name": asked.group(1).upper()})
            keys = _tables.get(asked.group(1).lower(), {}).get("keys", [])
            rows = [Row({"cid": number, "name": name, "type": "TEXT" if kind in ("VARCHAR2", "CLOB") else kind,
                         "notnull": int(nullable == "N"), "dflt_value": None, "pk": int(name in keys)})
                    for number, name, kind, nullable in cursor.fetchall()]
        return Result(rows, 0, ["cid", "name", "type", "notnull", "dflt_value", "pk"])

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        if self._raw is not None:
            self._pool.release(self._raw)
            self._raw = None

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, kind, error, trace) -> None:
        self._raw.rollback() if kind else self._raw.commit()


# ── Schema and pool ───────────────────────────────────────────────────────────

def _quietly(cursor: oracledb.Cursor, statement: str) -> bool:
    """Run one statement of setup. It returns False when the object was already there."""
    try:
        cursor.execute(statement)
        return True
    except oracledb.DatabaseError as error:
        if any(code in str(error) for code in ALREADY_EXISTS):
            return False
        raise


def _login(user: str) -> oracledb.Connection | None:
    try:
        return oracledb.connect(user=user, password=settings()["password"], dsn=settings()["dsn"],
                                tcp_connect_timeout=5)
    except oracledb.DatabaseError as error:
        if "ORA-01017" in str(error):              # the user is not there yet, or the password differs
            return None
        raise


def ensure_schema(identity: str) -> str:
    """Make sure the owner's schema exists, and return its name.

    An existing schema is used as it is. A missing one is created, which needs the
    database administrator's password once, in ``ORACLE_ADMIN_PASSWORD``.
    """
    user, found = schema_name(identity), None
    found = _login(user)
    if found is not None:
        found.close()
        return user
    chosen = settings()
    if not chosen["admin_password"]:
        raise RuntimeError(
            f"The schema {user} does not exist yet. Set ORACLE_ADMIN_PASSWORD once, so that the "
            "appbook can create it, and start the appbook again.")
    with oracledb.connect(user="sys", password=chosen["admin_password"], dsn=chosen["dsn"],
                          mode=oracledb.AUTH_MODE_SYSDBA, tcp_connect_timeout=5) as admin:
        with admin.cursor() as cursor:
            space = chosen["tablespace"]
            if not space:
                cursor.execute("SELECT COUNT(*) FROM dba_tablespaces WHERE tablespace_name = 'PPA_DATA'")
                space = "PPA_DATA" if cursor.fetchone()[0] else "USERS"
            _quietly(cursor, f'CREATE USER {user} IDENTIFIED BY "{chosen["password"]}" '
                             f"DEFAULT TABLESPACE {space} QUOTA UNLIMITED ON {space}")
            for grant in GRANTS:
                cursor.execute(f"GRANT {grant} TO {user}")
    return user


def pool_for(identity: str) -> oracledb.ConnectionPool:
    with _lock:
        user = schema_name(identity)
        if user not in _pools:
            ensure_schema(identity)
            _pools[user] = oracledb.create_pool(
                user=user, password=settings()["password"], dsn=settings()["dsn"], min=1, max=12,
                increment=1, ping_interval=0, getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=30_000)
        return _pools[user]


def connect(identity: str, trace: Callable[[str], None] | None = None) -> Connection:
    return Connection(pool_for(identity), trace)


def _add_columns(cursor: oracledb.Cursor, table: str) -> list[str]:
    """Give a table that an earlier build created the columns the portable schema has gained since."""
    cursor.execute("SELECT LOWER(column_name) FROM user_tab_cols WHERE table_name = :name",
                   {"name": table.upper()})
    present = {record[0] for record in cursor.fetchall()}
    added = []
    for item in _tables[table]["columns"]:
        if item["name"] not in present and not item["counter"]:
            # ORA-01430: another process added it first. A required number needs its default to be added.
            try:
                cursor.execute(f"ALTER TABLE {table} ADD ({_column(table, item)})")
                added.append(item["name"])
            except oracledb.DatabaseError as error:
                if "ORA-01430" not in str(error):
                    raise
    return added


def create_tables(identity: str, script: str) -> list[str]:
    """Create every table of the portable schema that is not there yet."""
    read_schema(script)
    made = []
    connection = pool_for(identity).acquire()
    try:
        with connection.cursor() as cursor:
            for table in _tables:
                if _quietly(cursor, table_ddl(table)):
                    made.append(table)
                else:
                    _add_columns(cursor, table)
            for index, table, columns in re.findall(
                    r"CREATE INDEX IF NOT EXISTS (\w+) ON (\w+)\((.*?)\);", script):
                _quietly(cursor, f"CREATE INDEX {index} ON {table} ({columns})")
        connection.commit()
    finally:
        pool_for(identity).release(connection)
    return made


def add_order(identity: str, names: Iterable[str]) -> None:
    """Give tables that something else created the column that records the order of insertion.
    LangGraph creates its own checkpoint tables; the explorer pages through them like any other."""
    connection = pool_for(identity).acquire()
    try:
        with connection.cursor() as cursor:
            for name in names:
                try:
                    cursor.execute(f"ALTER TABLE {name} ADD (seq NUMBER INVISIBLE GENERATED ALWAYS AS IDENTITY)")
                except oracledb.DatabaseError as error:
                    if "ORA-01430" not in str(error) and "ORA-00942" not in str(error):
                        raise                      # already there, or the table is not: both are fine
    finally:
        pool_for(identity).release(connection)


def tables(identity: str) -> list[str]:
    connection = connect(identity)
    try:
        found = connection.execute("SELECT LOWER(table_name) AS name FROM user_tables ORDER BY table_name")
        return [row["name"] for row in found.fetchall()]
    finally:
        connection.close()


def version(identity: str) -> str:
    connection = connect(identity)
    try:
        found = connection.execute(
            "SELECT version_full FROM product_component_version FETCH FIRST 1 ROWS ONLY")
        return found.fetchone()["version_full"]
    finally:
        connection.close()


async def checkpoint_pool(identity: str) -> oracledb.AsyncConnectionPool:
    """The pool that LangGraph's checkpoints use. It is separate, so a checkpoint never
    waits for a tool and a tool never waits for a checkpoint."""
    ensure_schema(identity)
    return oracledb.create_pool_async(
        user=schema_name(identity), password=settings()["password"], dsn=settings()["dsn"],
        min=1, max=8, increment=1, ping_interval=0,
        getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=30_000)


def close() -> None:
    with _lock:
        for pool in _pools.values():
            pool.close(force=True)
        _pools.clear()
