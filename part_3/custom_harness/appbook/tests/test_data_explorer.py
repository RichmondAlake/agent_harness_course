"""The data explorer is read-only, allowlisted and bounded."""
from __future__ import annotations

import json

from conftest import STORE, Api

from backend.core import explorer, store

REQUIRED = {"ppa_tasks", "ppa_focus_sessions", "ppa_contacts", "ppa_action_audit", "ppa_agent_sessions",
            "ppa_scratch_files", "ppa_memory_promotion_queue", "ppa_notifications", "ppa_automation_queue",
            "ppa_skill_registry", "ppa_tool_registry", "ppa_memories"}


def test_the_table_list_holds_only_allowlisted_tables(api: Api):
    listed = api.get("/api/data_explorer/tables")
    names = [item["name"] for item in listed["tables"]]
    assert names == list(explorer.listed()) and REQUIRED <= set(names)
    assert set(store.HARNESS_TABLES) | set(store.CHECKPOINT_TABLES) == set(names), "every owned table is covered"
    assert listed["access"] == "read-only" and listed["substrate"] == store.SUBSTRATE == STORE
    assert all(item["group"] and item["about"] and item["columns"] for item in listed["tables"]
               if item["database"] == "harness")
    assert not [name for name in names if "connection" in name or "secret" in name or "credential" in name]


def test_an_unknown_table_is_rejected(api: Api):
    for name in ("sqlite_master", "ppa_tasks; DROP TABLE ppa_tasks", "ppa_tasks--", "connections", "PPA_TASKS"):
        api.get(f"/api/data_explorer/tables/{name}/rows", expect=404)
        api.get(f"/api/data_explorer/tables/{name}/export", expect=404)
        api.get(f"/api/data_explorer/tables/{name}/rows/1", expect=404)
    assert api.get("/api/data_explorer/tables/ppa_skill_registry/rows")["total"] == 7, "and nothing was harmed"


def test_paging_limits_are_enforced(api: Api):
    contacts = api.get("/api/data_explorer/tables/ppa_contacts/rows?limit=100")
    assert contacts["total"] > 100 and len(contacts["rows"]) == 100 == contacts["limit"]
    api.get("/api/data_explorer/tables/ppa_contacts/rows?limit=101", expect=422)
    api.get("/api/data_explorer/tables/ppa_contacts/rows?limit=0", expect=422)
    api.get("/api/data_explorer/tables/ppa_contacts/rows?offset=-1", expect=422)
    second = api.get("/api/data_explorer/tables/ppa_contacts/rows?limit=10&offset=10")
    assert len(second["rows"]) == 10 and second["offset"] == 10
    first = api.get("/api/data_explorer/tables/ppa_contacts/rows?limit=10")
    assert not {row["rowid"] for row in first["rows"]} & {row["rowid"] for row in second["rows"]}
    assert listed_limit(api) == explorer.MAX_ROWS == 100


def listed_limit(api: Api) -> int:
    return api.get("/api/data_explorer/tables")["limits"]["rows_per_page"]


def test_sorting_and_searching_accept_columns_and_bound_values_only(api: Api):
    by_name = api.get("/api/data_explorer/tables/ppa_contacts/rows?sort=name&direction=asc&limit=20")
    names = [row["cells"]["name"] for row in by_name["rows"]]
    assert names == sorted(names) and by_name["sort"] == "name"
    api.get("/api/data_explorer/tables/ppa_contacts/rows?sort=name;DROP TABLE ppa_contacts", expect=400)
    api.get("/api/data_explorer/tables/ppa_contacts/rows?sort=rowid)--", expect=400)
    api.get("/api/data_explorer/tables/ppa_contacts/rows?direction=sideways", expect=422)
    domain = api.persona()["email"].split("@")[1]
    found = api.get(f"/api/data_explorer/tables/ppa_contacts/rows?search={domain}&limit=5")
    assert 0 < found["matched"] <= found["total"]
    assert all(domain in json.dumps(row["cells"]) for row in found["rows"])
    hostile = api.get("/api/data_explorer/tables/ppa_contacts/rows?search=%25' OR '1'='1")
    assert hostile["matched"] == 0 and hostile["total"] == by_name["total"]


def test_long_values_are_cut_in_the_grid_and_whole_on_demand(api: Api):
    skills = api.get("/api/data_explorer/tables/ppa_skill_registry/rows")
    cell = skills["rows"][0]["cells"]["body"]
    assert cell["truncated"] and cell["kind"] == "text" and len(cell["preview"]) <= explorer.PREVIEW
    whole = api.get(f"/api/data_explorer/tables/ppa_skill_registry/rows/{skills['rows'][0]['rowid']}")
    assert whole["values"]["body"]["length"] == cell["length"] == len(whole["values"]["body"]["value"])
    tools = api.get("/api/data_explorer/tables/ppa_tool_registry/rows?limit=1")
    schema = api.get(f"/api/data_explorer/tables/ppa_tool_registry/rows/{tools['rows'][0]['rowid']}")
    assert schema["values"]["input_schema"]["kind"] == "json"
    assert isinstance(schema["values"]["input_schema"]["value"], dict)
    api.get("/api/data_explorer/tables/ppa_tool_registry/rows/999999", expect=404)


def test_tables_that_started_empty_fill_and_are_marked_as_changed(api: Api):
    before = {item["name"]: item for item in api.get("/api/data_explorer/tables")["tables"]}
    assert before["ppa_tasks"]["row_count"] == before["ppa_action_audit"]["row_count"] == 0
    api.post("/api/inbox_triage/extract")
    api.post("/api/focus_sessions/start", {"demo_seconds": 60})
    paused = api.turn("Time-block my top three tasks for today.", thread_id="explorer")
    after = {item["name"]: item for item in api.get("/api/data_explorer/tables")["tables"]}
    for name in ("ppa_tasks", "ppa_action_audit", "ppa_automation_queue", "ppa_focus_sessions",
                 "ppa_agent_runs", "checkpoints"):
        assert after[name]["row_count"] > before[name]["row_count"], f"{name} should have filled"
        assert after[name]["writes"] > before[name]["writes"], f"{name} should be marked as changed"
    newest = api.get("/api/data_explorer/tables/ppa_action_audit/rows?limit=1")["rows"][0]
    assert newest["cells"]["action_id"] == paused["pending_actions"][-1]["action_id"], "newest first"
    checkpoint = api.get("/api/data_explorer/tables/checkpoints/rows?limit=1")["rows"][0]
    # The local saver stores a checkpoint as bytes. Oracle stores it as JSON.
    assert checkpoint["cells"]["checkpoint"]["kind"] == ("json" if STORE.startswith("Oracle") else "binary")
    opened = api.get(f"/api/data_explorer/tables/checkpoints/rows/{checkpoint['rowid']}")
    assert opened["values"]["checkpoint"]["kind"] == "json", "the blob is decoded for reading"
    api.post("/api/focus_sessions/stop", {"reason": "test"})


def test_the_explorer_cannot_write(api: Api):
    for method in ("post", "put", "patch", "delete"):
        response = getattr(api.client, method)("/api/data_explorer/tables/ppa_tasks/rows")
        assert response.status_code == 405
    exported = api.get("/api/data_explorer/tables/ppa_skill_registry/export")
    assert len(exported["rows"]) == 7 and exported["limit"] == explorer.EXPORT_ROWS
