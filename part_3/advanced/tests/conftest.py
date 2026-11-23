"""Offline by default. Tests that need Oracle AI Database skip when it is not reachable."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ADVANCED = Path(__file__).resolve().parents[1]
for folder in (ADVANCED / "deep_research" / "appbook" / "backend", ADVANCED / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


def load_harness(track: str, module: str):
    """Import a module of the ``harness`` package under ``<track>/appbook/backend``."""
    import importlib
    backend = ADVANCED / track / "appbook" / "backend"
    for name in list(sys.modules):
        if name == "harness" or name.startswith("harness."):
            if str(backend) not in str(getattr(sys.modules[name], "__file__", "") or ""):
                del sys.modules[name]
    sys.path[:] = [p for p in sys.path if "appbook/backend" not in p]
    sys.path.insert(0, str(backend))
    return importlib.import_module(module)
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")


def oracle_available() -> bool:
    from shared import oracle
    return oracle.reachable(timeout=1.0)


needs_oracle = pytest.mark.skipif(not oracle_available(), reason="Oracle AI Database is not reachable")
