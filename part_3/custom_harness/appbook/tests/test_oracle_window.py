"""The window on Oracle AI Database: read-only, optional, and strict about identifiers."""
from __future__ import annotations

import array
import os
from datetime import datetime
from decimal import Decimal

import pytest
from conftest import Api

from backend.core import oracle_window


def test_with_no_database_the_window_says_so_and_answers_200(api: Api):
    answer = api.get("/api/oracle")
    assert answer["reachable"] is False
    assert "cannot be reached" in answer["detail"] and "notebook" in answer["detail"]
    assert answer["access"].startswith("read-only") and answer["user"]
    one = api.get("/api/oracle/objects/PPA_TASKS")
    assert one["reachable"] is False and "rows" not in one
    for body in (answer, one):
        assert "password" not in str(body).lower()
        assert oracle_window.settings.oracle_password not in str(body), "the password is never part of an answer"
    assert api.get("/api/status")["ready"], "nothing else depends on Oracle"
    assert api.turn("Add a task: check the window")["status"] == "completed"


def test_an_identifier_must_come_from_the_data_dictionary():
    known = {"PPA_TASKS", "DR$INDEX$I", "PPA_V_OPEN_TASKS"}
    assert oracle_window.quoted("PPA_TASKS", known) == '"PPA_TASKS"'
    assert oracle_window.quoted("DR$INDEX$I", known) == '"DR$INDEX$I"'
    for name in ("PPA_TASK", "ppa_tasks", "PPA_TASKS; DROP TABLE PPA_TASKS", 'PPA_TASKS" --', "USER_USERS", ""):
        with pytest.raises(oracle_window.UnknownObject):
            oracle_window.quoted(name, known)
    with pytest.raises(oracle_window.UnknownObject):
        oracle_window.quoted('BAD"NAME', {'BAD"NAME'})


def test_objects_are_grouped_by_what_the_dictionary_says():
    names = ["PPA_TASKS", "PPA_V_OPEN_TASKS", "CHECKPOINTS", "CHECKPOINT_WRITES", "AGENT_MEMORY_STORES",
             "STORE_MEMORY", "STORE_THREAD", "STORE_RECORD_CHUNKS", "DR$STORE_I$K", "OTHER_MEMORY"]
    prefixes = oracle_window._memory_prefixes(names)
    assert prefixes == ["STORE"], "a prefix owns a MEMORY and a THREAD table"
    assert oracle_window.group_of("PPA_TASKS", "table", prefixes) == "Harness tables"
    assert oracle_window.group_of("PPA_V_OPEN_TASKS", "view", prefixes) == "Governed views"
    assert oracle_window.group_of("CHECKPOINT_WRITES", "table", prefixes) == "LangGraph checkpoints"
    assert oracle_window.group_of("STORE_RECORD_CHUNKS", "table", prefixes) == "Oracle Agent Memory"
    assert oracle_window.group_of("AGENT_MEMORY_STORES", "table", prefixes) == "Oracle Agent Memory"
    assert oracle_window.group_of("DR$STORE_I$K", "table", prefixes) == "Maintained by the database"
    assert oracle_window.group_of("USER_SCHEDULER_JOBS", "dictionary view", prefixes) == "Scheduler and model"


def test_the_newest_rows_are_chosen_by_a_time_column():
    def columns(*pairs):
        return [{"name": name, "type": kind} for name, kind in pairs]

    assert oracle_window.newest_by(columns(("ID", "NUMBER"), ("UPDATED_AT", "TIMESTAMP(6)"),
                                           ("CREATED_AT", "TIMESTAMP(6) WITH TIME ZONE"))) == "CREATED_AT"
    assert oracle_window.newest_by(columns(("ID", "NUMBER"), ("DUE", "DATE"))) == "DUE"
    assert oracle_window.newest_by(columns(("THREAD_ID", "VARCHAR2"), ("CHECKPOINT_ID", "VARCHAR2"))) == "CHECKPOINT_ID"
    assert oracle_window.newest_by(columns(("KEY", "VARCHAR2"), ("VALUE", "VARCHAR2"))) is None


def test_vectors_and_large_objects_are_shown_by_their_size_and_beginning():
    vector = oracle_window.shape(array.array("f", [0.25, -0.5, 1.0, 2.0, 3.0, 4.0]), "VECTOR")
    assert vector == {"kind": "vector", "dimension": 6, "format": "f", "first": [0.25, -0.5, 1.0, 2.0]}
    text = oracle_window.shape("x" * 200, "CLOB", 5000)
    assert text["kind"] == "clob" and text["length"] == 5000 and text["truncated"] and len(text["first"]) == 200
    binary = oracle_window.shape(bytes([0, 255, 16]), "BLOB", 3)
    assert binary["kind"] == "blob" and binary["first"] == "00ff10" and binary["encoding"] == "hexadecimal"
    assert oracle_window.shape(None, "CLOB", None) is None
    assert oracle_window.shape(Decimal("7"), "NUMBER") == 7 and oracle_window.shape(Decimal("7.5"), "NUMBER") == 7.5
    assert oracle_window.shape(datetime(2026, 9, 29, 14, 0), "TIMESTAMP(6)") == "2026-09-29T14:00:00"
    assert oracle_window.shape({"a": [1, 2]}, "JSON") == {"kind": "json", "value": {"a": [1, 2]}}


def test_the_tests_never_reach_a_real_database():
    assert os.environ["PPA_ORA_DSN"].startswith("127.0.0.1:1/")
    oracle_window.forget()
    assert oracle_window.probe()["reachable"] is False
