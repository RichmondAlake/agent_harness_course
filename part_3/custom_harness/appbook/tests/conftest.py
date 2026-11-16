"""Offline test harness: scripted responder, practice workspace, throwaway state.

Nothing here needs credentials or a network. The gateway is launched as a
subprocess on a free port with its home folder inside a temporary directory, so
a test can never touch a real connection store.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

APPBOOK = Path(__file__).resolve().parents[1]
SHARED = APPBOOK.parents[1] / "_shared"
STATE = Path(tempfile.mkdtemp(prefix="ppa-appbook-tests-"))


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


os.environ.update({
    "PPA_RESPONDER": "scripted", "PPA_DATA_DIR": str(STATE), "PPA_HOME": str(STATE / "ppa_home"),
    "PPA_MCP_PORT": str(_free_port()), "PPA_MCP_TOKEN": "appbook-test-token",
    "PPA_OWNER_EMAIL": "owner@appbook-tests.example", "PPA_SCHEDULER_POLL_SECONDS": "0.2",
    "PPA_TRIGGER_POLL_SECONDS": "3600", "PPA_SAFE_MODE": "1",
    "PPA_ORA_DSN": "127.0.0.1:1/NO_DATABASE_IN_TESTS",     # a closed port: the tests need no database
    # The suite runs on the local store unless it is asked to run on Oracle AI Database:
    #   PPA_TEST_SUBSTRATE=oracle python -m pytest tests
    "PPA_SUBSTRATE": os.environ.get("PPA_TEST_SUBSTRATE", "local"),
    "PPA_APPBOOK_ORA_USER": "PPA3_TEST",      # the suite has schemas of its own, and empties them
})
# What the appbook must call its store, on the substrate this run of the suite uses.
STORE = "Oracle AI Database" if os.environ["PPA_SUBSTRATE"] == "oracle" else "Local store"
for secret in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "TYPESAFE_API_KEY"):
    os.environ[secret] = ""
for switch in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
    os.environ[switch] = "false"            # offline means offline: no test sends a trace anywhere
for folder in (str(APPBOOK), str(SHARED)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import bootstrap  # noqa: E402,F401  (puts the shared workspace and policy on the path)
import policy  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


class Api:
    """A thin wrapper so tests read as requests and answers."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def get(self, path: str, expect: int = 200) -> dict:
        response = self.client.get(path)
        assert response.status_code == expect, f"GET {path}: {response.status_code} {response.text[:300]}"
        return response.json()

    def post(self, path: str, body: dict | None = None, expect: int = 200) -> dict:
        response = self.client.post(path, json=body or {})
        assert response.status_code == expect, f"POST {path}: {response.status_code} {response.text[:300]}"
        return response.json()

    def read(self, tool: str, **arguments) -> dict:
        """One read through MCP, as the server returned it."""
        return self.post("/api/systems_of_record/read", {"name": tool, "arguments": arguments})["raw_mcp_result"]

    def turn(self, message: str, **fields) -> dict:
        return self.post("/api/assistant/turn", {"message": message, **fields})

    def wait_for(self, check, seconds: float = 12.0, what: str = "the condition"):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = check()
            if found:
                return found
            time.sleep(0.2)
        jobs = [(item["kind"], item["state"], item["fires_at"], item["error"])
                for item in self.get("/api/routines/jobs")["jobs"]] if self.get("/api/status").get("ready") else []
        raise AssertionError(f"Timed out after {seconds} s waiting for {what}. Jobs: {jobs}")

    def persona(self) -> dict:
        return self.get("/api/status")["owner"]

    def now(self) -> datetime:
        return datetime.fromisoformat(self.get("/api/clock")["now"])


@pytest.fixture(scope="module")
def started():
    """One application lifetime per test module: gateway, scheduler and graph included."""
    with TestClient(app) as client:
        api = Api(client)
        api.wait_for(lambda: api.get("/api/status").get("ready"), 60, "the harness to start")
        yield api


@pytest.fixture()
def api(started: Api) -> Api:
    """Every test starts from empty harness state on the practice workspace."""
    started.post("/api/reset", {"confirm": "reset"})
    return started


@pytest.fixture()
def rules(api: Api) -> dict:
    return api.get("/api/calendar_intel/status")["day"]["rules"]


def minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


__all__ = ["Api", "minutes", "policy"]
