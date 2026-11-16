"""The reference architecture: one structure, checked for gaps and for live status."""
from __future__ import annotations

import os

from conftest import STORE, Api

VOCABULARY = {"connected", "configured", "fallback", "off", "not_configured", "failing"}


def _by_id(payload: dict) -> dict[str, dict]:
    return {item["id"]: item for item in payload["components"]}


def test_every_component_is_described_placed_and_checked(api: Api):
    from backend.core import architecture

    lanes = {lane["id"] for lane in architecture.LANES}
    identities = [part["id"] for part in architecture.COMPONENTS]
    assert len(identities) == len(set(identities)), "component ids are unique"
    assert set(architecture.CHECKS) == set(identities), "one status check for each component, no more"
    for part in architecture.COMPONENTS:
        assert part["lane"] in lanes, part["id"]
        for field in ("title", "label", "what", "why", "technology"):
            assert len(part[field].strip()) > 3, f"{part['id']} has no {field}"
        assert part["what"].rstrip().endswith("."), f"{part['id']}: a description is a sentence"
        assert part["artefacts"]["files"], f"{part['id']} names no file"
    assert {lane["id"] for lane in architecture.LANES} == {part["lane"] for part in architecture.COMPONENTS}


def test_edges_paths_and_the_ledger_refer_to_real_components(api: Api):
    from backend.core import architecture

    identities = {part["id"] for part in architecture.COMPONENTS}
    edges = {(source, target) for source, target, _, _ in architecture.EDGES}
    assert len(edges) == len(architecture.EDGES), "no edge is declared twice"
    for source, target, label, _ in architecture.EDGES:
        assert source in identities and target in identities and source != target, (source, target)
        assert label.strip()
    assert len(architecture.PATHS) >= 3
    for path in architecture.PATHS:
        assert path["title"] and path["about"] and path["steps"], path["id"]
        for step in path["steps"]:
            assert step["title"] and step["text"].rstrip().endswith("."), (path["id"], step["title"])
            assert step["components"], (path["id"], step["title"])
            assert set(step["components"]) <= identities, (path["id"], step["title"])
            for source, target in step["edges"]:
                assert (source, target) in edges, f"{path['id']}: {source} -> {target} is not an edge"
                assert {source, target} <= set(step["components"]), \
                    f"{path['id']} / {step['title']}: {source} -> {target} joins a part the step leaves dark"
    for row in architecture.LEDGER:
        assert row["part"] == "" or row["part"] in identities, row["concern"]


def test_the_diagram_covers_every_table_node_and_system(api: Api):
    payload = api.get("/api/architecture")
    parts = _by_id(payload)
    shown = {table for part in parts.values() for table in part["artefacts"]["tables"]}
    owned = {item["name"] for item in api.get("/api/data_explorer/tables")["tables"]}
    assert owned <= shown, f"tables missing from the diagram: {sorted(owned - shown)}"
    loop = api.get("/api/the_loop/status")["nodes"]
    assert [part["id"] for part in payload["components"] if part["lane"] == "loop"] == loop
    offered = api.get("/api/connections/status")["providers"]
    connectors = {(part["system"], part["id"]) for part in parts.values() if part.get("system")}
    assert connectors == {(system, item["id"]) for system, items in offered.items() for item in items}
    chapters = {part["jump"]["chapter"] for part in parts.values() if part["jump"]["chapter"]}
    assert chapters <= {"assistant", "systems_of_record", "memory_layer", "governed_meaning",
                        "inbox_triage", "calendar_intel", "focus_sessions", "skills", "approvals",
                        "the_loop", "routines", "weekly_review", "system_one",
                        "context_cost", "learning", "scorecard"}


def test_status_comes_from_checks_and_hides_secrets(api: Api):
    payload = api.get("/api/architecture")
    parts = _by_id(payload)
    assert {part["status"] for part in parts.values()} <= VOCABULARY
    assert set(payload["statuses"]) == VOCABULARY
    assert not [part["id"] for part in parts.values() if part["status"] == "failing"], \
        {part["id"]: part["detail"] for part in parts.values() if part["status"] == "failing"}
    # No credentials in this test run: the model and web search say so, and stand-ins are named.
    assert parts["claude"]["status"] == "not_configured"
    assert parts["scripted"]["status"] == "fallback"
    assert parts["tavily"]["status"] == "not_configured"
    assert parts["embedding"]["status"] == "fallback" and parts["memory_provider"]["status"] == "fallback"
    assert parts["system_one"]["status"] == "fallback" and "rules decide" in parts["system_one"]["detail"]
    assert parts["database"]["status"] == "connected" and parts["database"]["detail"].startswith(STORE)
    assert parts["practice"]["status"] == "connected"
    assert {parts[name]["status"] for name in ("imap", "google", "ics", "notion", "folder")} == {"not_configured"}
    assert os.environ["PPA_MCP_TOKEN"] not in str(payload), "the gateway token never leaves the backend"
    assert parts["langsmith"]["status"] == "off", "tests switch tracing off"
    assert parts["gateway"]["version"].startswith("mcp ")
    assert "langgraph" in parts["call_model"]["version"]


def test_status_follows_the_running_system(api: Api):
    before = api.get("/api/architecture/status")["components"]
    assert before["t_tasks"]["metric"] == {"label": "rows", "value": 0}
    assert before["safe_mode"]["status"] == "connected" and before["scheduler"]["status"] == "connected"
    assert before["human_review"]["metric"]["value"] == 0

    api.turn("Add a task: renew the domain")
    api.post("/api/connections/safe_mode", {"enabled": False})
    api.post("/api/routines/automation", {"enabled": False})
    after = api.get("/api/architecture/status")["components"]
    assert after["t_tasks"]["metric"]["value"] == 1
    assert after["persist"]["metric"]["value"] == before["persist"]["metric"]["value"] + 1
    assert after["safe_mode"]["status"] == "off"
    assert {after[name]["status"] for name in ("scheduler", "routines", "triggers")} == {"off"}

    api.post("/api/connections/safe_mode", {"enabled": True})
    api.post("/api/routines/automation", {"enabled": True})
    again = api.get("/api/architecture/status")["components"]
    assert again["safe_mode"]["status"] == "connected" and again["scheduler"]["status"] == "connected"


def test_asking_for_status_is_not_activity(api: Api):
    """The view asks again whenever a table changes, so its own reads must not count as a change."""
    api.get("/api/architecture/status")
    before = api.get("/api/data_explorer/activity/recent?limit=200")["events"]
    newest = before[0]["sequence"] if before else 0
    api.get("/api/architecture/status")
    api.get("/api/architecture")
    after = [item for item in api.get("/api/data_explorer/activity/recent?limit=200")["events"]
             if item["sequence"] > newest]
    assert [item for item in after if item["data"]["route"].startswith("/api/architecture")] == []
    api.get("/api/assistant/tasks")
    later = [item for item in api.get("/api/data_explorer/activity/recent?limit=200")["events"]
             if item["sequence"] > newest]
    assert any(item["data"]["table"] == "ppa_tasks" for item in later), "other reads are still reported"


def test_the_oracle_window_is_off_when_there_is_no_database(api: Api):
    parts = _by_id(api.get("/api/architecture"))
    assert parts["oracle"]["status"] == "off" and "Not reachable" in parts["oracle"]["detail"]
    assert "Nothing in the appbook depends on it" in parts["oracle"]["detail"]
    assert parts["database"]["status"] == "connected", "the appbook's own store is not affected"
