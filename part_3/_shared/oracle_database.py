"""Oracle AI Database for Part 3: one place that knows how to reach it, prepare it and talk to it.

The notebooks and the appbooks of the advanced track import this file, so the
database is set up the same way everywhere. Any other part of Part 3 can use it
too: the account, the port and the container are read from the environment.

    from oracle_database import start_database, ensure_schema, ensure_embedding_model, rows, execute, ddl


The schema is created through the database container's operating-system
authentication (``sqlplus / as sysdba`` inside the container), so no SYS
password is needed on a machine that runs the practice database image. When the
database is not in Docker on this machine, ``ORACLE_ADMIN_PASSWORD`` is used
instead. Everything here is idempotent: run it twice and nothing changes.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import oracledb
import requests

oracledb.defaults.fetch_lobs = False

ONNX_URL = ("https://objectstorage.us-ashburn-1.oraclecloud.com/n/adwc4pm/b/"
            "OML-Resources/o/all_MiniLM_L12_v2.onnx")
GRANTS = ["CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "CREATE PROCEDURE", "CREATE TRIGGER",
          "CREATE JOB", "CREATE MINING MODEL", "CREATE SEQUENCE", "CREATE DOMAIN", "CREATE PROPERTY GRAPH",
          "SELECT_CATALOG_ROLE",
          "EXECUTE ON DBMS_SCHEDULER", "EXECUTE ON DBMS_VECTOR", "EXECUTE ON DBMS_VECTOR_CHAIN"]
ALREADY_THERE = ("ORA-01543", "ORA-01920", "ORA-00955", "ORA-01430", "ORA-02260")
POOL = dict(min=1, max=8, increment=1, ping_interval=0,
            getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=120_000)   # a small database can be slow under load


@dataclass(frozen=True)
class OracleConfig:
    dsn: str = os.getenv("ADV_ORA_DSN", "127.0.0.1:1524/FREEPDB1")
    user: str = os.getenv("ADV_ORA_USER", "PPA_ADVANCED")
    password: str = os.getenv("ADV_ORA_PWD", "PpaAdvanced_2026!")
    container: str = os.getenv("ADV_ORACLE_CONTAINER", "ppa-custom-oracle-26ai")
    pdb: str = os.getenv("ADV_ORA_PDB", "FREEPDB1")
    tablespace: str = os.getenv("ADV_ORA_TABLESPACE", "PPA_DATA")
    embed_model: str = "ALL_MINILM_L12_V2"
    model_cache: Path = Path(os.getenv("ADV_MODEL_CACHE", Path.home() / ".ppa_workshop" / "models"))


ORA = OracleConfig()
_pools: dict[str, oracledb.ConnectionPool] = {}


def reachable(timeout: float = 3.0) -> bool:
    import socket
    host, rest = ORA.dsn.split(":", 1)
    try:
        with socket.create_connection((host, int(rest.split("/")[0])), timeout=timeout):
            return True
    except OSError:
        return False


def _container_running() -> bool:
    found = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", ORA.container],
                           capture_output=True, text=True)
    return found.returncode == 0 and found.stdout.strip() == "true"


def admin_sql(statements: list[str]) -> list[str]:
    """Run statements as the administrator. Returns the ORA- lines that were not 'already there'."""
    if _container_running():
        def block(statement: str) -> str:
            plsql = statement.lstrip().upper().startswith(("DECLARE", "BEGIN"))
            return statement.rstrip().rstrip(";") + (";\n/" if plsql else ";")
        script = "\n".join(["SET HEADING OFF FEEDBACK OFF ECHO OFF",
                            f"ALTER SESSION SET CONTAINER = {ORA.pdb};",
                            *(block(s) for s in statements), "EXIT"])
        done = subprocess.run(["docker", "exec", "-i", ORA.container, "sqlplus", "-s", "/ as sysdba"],
                              input=script, capture_output=True, text=True, timeout=300)
        return [line.strip() for line in done.stdout.splitlines()
                if line.startswith("ORA-") and not line.startswith(ALREADY_THERE)]
    password = os.getenv("ORACLE_ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError("The database container is not running here and ORACLE_ADMIN_PASSWORD is "
                           "not set, so the schema cannot be created.")
    problems = []
    with oracledb.connect(user="sys", password=password, dsn=ORA.dsn,
                          mode=oracledb.AUTH_MODE_SYSDBA) as admin, admin.cursor() as cursor:
        for statement in statements:
            try:
                cursor.execute(statement.rstrip(";"))
            except oracledb.DatabaseError as error:
                if not str(error).startswith(ALREADY_THERE):
                    problems.append(str(error).splitlines()[0])
        admin.commit()
    return problems


def start_database(wait_seconds: int = 600) -> bool:
    """Start Oracle AI Database Free in Docker when it is not answering, and wait for it.

    An existing container is started. When there is none, one is created from the
    Free image, which takes a few minutes the first time.
    """
    if reachable():
        return True
    port = ORA.dsn.split(":")[1].split("/")[0]
    if subprocess.run(["docker", "start", ORA.container], capture_output=True).returncode:
        subprocess.run(["docker", "run", "-d", "--name", ORA.container, "-p", f"127.0.0.1:{port}:1521",
                        "-e", "ORACLE_PWD=" + os.getenv("ORACLE_ADMIN_PASSWORD", "ChangeMe_2026!"),
                        "-v", f"{ORA.container}-data:/opt/oracle/oradata",
                        "container-registry.oracle.com/database/free:latest-lite"], check=True, capture_output=True)
    deadline = time.monotonic() + wait_seconds
    while (not _container_running() or admin_sql(["BEGIN NULL; END;"])) and time.monotonic() < deadline:
        time.sleep(5)
    return reachable()


def ensure_schema() -> dict:
    """The tablespace, the user and its grants. Safe to call on every start."""
    try:
        with oracledb.connect(user=ORA.user, password=ORA.password, dsn=ORA.dsn):
            return {"user": ORA.user, "created": False}
    except oracledb.DatabaseError:
        pass
    tablespace = "\n".join([
        "DECLARE d VARCHAR2(400);",
        "BEGIN",
        "  SELECT REGEXP_REPLACE(file_name, '[^/]+$', '') INTO d FROM dba_data_files",
        "   WHERE tablespace_name = 'SYSTEM' FETCH FIRST 1 ROW ONLY;",
        f"  EXECUTE IMMEDIATE 'CREATE TABLESPACE {ORA.tablespace} DATAFILE ''' || d || "
        f"'{ORA.tablespace.lower()}01.dbf'' SIZE 512M AUTOEXTEND ON NEXT 128M MAXSIZE 8G "
        "SEGMENT SPACE MANAGEMENT AUTO';",
        "EXCEPTION WHEN OTHERS THEN IF SQLCODE NOT IN (-1543) THEN RAISE; END IF;",
        "END;"])
    problems = admin_sql([
        tablespace,
        f'CREATE USER {ORA.user} IDENTIFIED BY "{ORA.password}" '
        f"DEFAULT TABLESPACE {ORA.tablespace} QUOTA UNLIMITED ON {ORA.tablespace}",
        *(f"GRANT {grant} TO {ORA.user}" for grant in GRANTS)])
    if problems:
        raise RuntimeError("The schema could not be created: " + "; ".join(problems))
    with oracledb.connect(user=ORA.user, password=ORA.password, dsn=ORA.dsn):
        return {"user": ORA.user, "created": True}


def pool(name: str = "app", **overrides) -> oracledb.ConnectionPool:
    if name not in _pools:
        _pools[name] = oracledb.create_pool(user=ORA.user, password=ORA.password, dsn=ORA.dsn,
                                            **{**POOL, **overrides})
    return _pools[name]


def _patient(work):
    """One retry when the pool or the network let a call down; the database is small and shared."""
    import time
    try:
        return work()
    except oracledb.DatabaseError as error:
        if not str(error).startswith(("DPY-4005", "DPY-4011", "ORA-04036", "ORA-03113")):
            raise
        time.sleep(3)
        return work()


def rows(sql: str, binds=None) -> list[dict]:
    def work():
        with pool().acquire() as connection, connection.cursor() as cursor:
            cursor.execute(sql, binds or {})
            names = [column[0].lower() for column in cursor.description]
            return [dict(zip(names, record)) for record in cursor.fetchall()]
    return _patient(work)


def execute(sql: str, binds=None, many: list | None = None) -> int:
    def work():
        with pool().acquire() as connection, connection.cursor() as cursor:
            if many is not None:
                cursor.executemany(sql, many)
            else:
                cursor.execute(sql, binds or {})
            connection.commit()
            return cursor.rowcount
    return _patient(work)


def ddl(statement: str) -> None:
    """Create something, and do nothing when it already exists."""
    with pool().acquire() as connection, connection.cursor() as cursor:
        try:
            cursor.execute(statement)
        except oracledb.DatabaseError as error:
            if not str(error).startswith(ALREADY_THERE):
                raise


def ensure_embedding_model() -> dict:
    """The ONNX sentence embedder inside the database, loaded once per schema."""
    if rows("SELECT 1 FROM user_mining_models WHERE model_name = :n", {"n": ORA.embed_model}):
        return {"model": ORA.embed_model, "loaded": False}
    ORA.model_cache.mkdir(parents=True, exist_ok=True)
    cached = ORA.model_cache / "all_MiniLM_L12_v2.onnx"
    if not cached.exists():
        cached.write_bytes(requests.get(ONNX_URL, timeout=600).content)
    metadata = {"function": "embedding", "embeddingOutput": "embedding", "input": {"input": ["DATA"]}}
    with pool().acquire() as connection, connection.cursor() as cursor:
        blob = connection.createlob(oracledb.DB_TYPE_BLOB)
        blob.write(cached.read_bytes())
        cursor.execute("BEGIN DBMS_VECTOR.LOAD_ONNX_MODEL(:n, :d, JSON(:m)); END;",
                       {"n": ORA.embed_model, "d": blob, "m": json.dumps(metadata)})
        connection.commit()
    return {"model": ORA.embed_model, "loaded": True}


EMBED = f"VECTOR_EMBEDDING({ORA.embed_model} USING :text AS DATA)"


def embedding(text: str) -> list[float]:
    return rows(f"SELECT {EMBED} AS v FROM dual", {"text": text[:4000]})[0]["v"]


def version() -> str:
    return rows("SELECT version_full AS v FROM product_component_version FETCH FIRST 1 ROW ONLY")[0]["v"]


def close() -> None:
    for name, found in list(_pools.items()):
        found.close(force=True)
        _pools.pop(name, None)
