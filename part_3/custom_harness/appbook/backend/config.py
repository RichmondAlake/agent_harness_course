"""Central configuration for the PPA custom-harness appbook."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
PART_3_DIR = APP_DIR.parents[1]
COURSE_ROOT = APP_DIR.parents[2]
FRONTEND_DIR = APP_DIR / "frontend"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


for candidate in (COURSE_ROOT / ".env", APP_DIR / ".env"):
    _load_env(candidate)

SHARED_DIR = Path(os.environ.get("PPA_SHARED_DIR") or PART_3_DIR / "_shared")
DATA_DIR = Path(os.environ.get("PPA_DATA_DIR") or APP_DIR / "data")

# Governed definitions are shared by every Part 3 build and imported, never copied.
if str(SHARED_DIR / "runtime") not in sys.path:
    sys.path.insert(0, str(SHARED_DIR / "runtime"))


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
    effort: str = os.environ.get("PPA_EFFORT", "medium")
    responder: str = os.environ.get("PPA_RESPONDER", "auto").lower()
    tavily_api_key: str = os.environ.get("TAVILY_API_KEY", "")
    memory_backend: str = os.environ.get("PPA_MEMORY_BACKEND", "local").lower()
    gateway_script: Path = Path(os.environ.get("PPA_GATEWAY_SCRIPT")
                                or SHARED_DIR / "mcp" / "workspace_mcp_server.py")
    mcp_host: str = os.environ.get("PPA_MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.environ.get("PPA_MCP_PORT", "8951"))
    mcp_token: str = os.environ.get("PPA_MCP_TOKEN", "ppa3-local-token")
    graph_max_iterations: int = int(os.environ.get("PPA_GRAPH_MAX_ITERATIONS", "12"))
    model_timeout_seconds: int = int(os.environ.get("PPA_MODEL_TIMEOUT_SECONDS", "240"))
    scheduler_poll_seconds: float = float(os.environ.get("PPA_SCHEDULER_POLL_SECONDS", "0.5"))
    trigger_poll_seconds: float = float(os.environ.get("PPA_TRIGGER_POLL_SECONDS", "60"))
    triage_window: int = int(os.environ.get("PPA_TRIAGE_WINDOW", "25"))
    # The notebook's Oracle AI Database, read by the data explorer and never written. These are the
    # notebook's documented defaults for a database that runs on this machine.
    oracle_dsn: str = os.environ.get("PPA_ORA_DSN", "127.0.0.1:1524/FREEPDB1")
    oracle_user: str = os.environ.get("PPA_ORA_USER", "PPA3_AGENT")
    oracle_password: str = os.environ.get("PPA_ORA_PWD", "Ppa3Agent_2026!")
    oracle_connect_seconds: float = float(os.environ.get("PPA_ORA_CONNECT_SECONDS", "3"))
    # List prices for claude-opus-5-5, in US dollars per million tokens. The cost ledger multiplies by these.
    price_fresh_input: float = float(os.environ.get("PPA_PRICE_FRESH_INPUT", "4.00"))
    price_cache_write: float = float(os.environ.get("PPA_PRICE_CACHE_WRITE", "5.00"))
    price_cache_read: float = float(os.environ.get("PPA_PRICE_CACHE_READ", "0.20"))
    price_output: float = float(os.environ.get("PPA_PRICE_OUTPUT", "20.00"))

    @property
    def claude_available(self) -> bool:
        """Claude answers only when a key exists and the operator has not forced the script."""
        return bool(self.anthropic_api_key) and self.responder != "scripted"

    @property
    def mcp_base_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}"


settings = Settings()
