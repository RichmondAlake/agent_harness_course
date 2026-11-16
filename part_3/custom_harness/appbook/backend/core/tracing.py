"""Whether LangSmith tracing is switched on. The appbook only reports it.

LangChain and LangGraph send a trace of every graph step, model call and tool
result to LangSmith when the environment sets ``LANGSMITH_TRACING`` to true
and a key is present. No appbook code starts, stops or changes that. This
module reads the same switch the libraries read, so the header and the
architecture view can say plainly that traces are leaving the machine.
"""
from __future__ import annotations

import os
from typing import Any

from langsmith import utils

KEY_NAMES = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")


def requested() -> bool:
    """Whether the environment asks LangChain to trace."""
    return utils.tracing_is_enabled() is True


def key_configured() -> bool:
    return any(os.environ.get(name) for name in KEY_NAMES)


def active() -> bool:
    return requested() and key_configured()


def status() -> dict[str, Any]:
    if not requested():
        detail = "off: LANGSMITH_TRACING is not set to true"
    elif not key_configured():
        detail = "requested, but no LangSmith key is configured"
    else:
        detail = "on: graph steps, model calls and tool results are sent to LangSmith"
    return {"provider": "LangSmith", "requested": requested(), "configured": key_configured(),
            "active": active(), "detail": detail}
