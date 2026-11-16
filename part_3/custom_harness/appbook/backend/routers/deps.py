"""Shared router dependencies."""
from fastapi import HTTPException

from backend.core import runtime


async def ready() -> None:
    """Every chapter waits for the harness to finish starting."""
    try:
        await runtime.ready()
    except Exception as exc:
        raise HTTPException(503, f"The harness could not start: {exc}") from exc
