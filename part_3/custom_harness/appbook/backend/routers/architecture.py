"""Chapter 1: the reference architecture, with a live status on every component."""
from fastapi import APIRouter, Depends, Request

from backend.core import architecture
from backend.routers.deps import ready

router = APIRouter(prefix="/api/architecture", tags=["architecture"], dependencies=[Depends(ready)])


def _routes(request: Request) -> int:
    """How many API paths the application documents for itself."""
    return len(request.app.openapi()["paths"])


@router.get("")
async def read(request: Request):
    """Lanes, components, edges, request paths and the ledger, checked now."""
    return await architecture.snapshot(_routes(request))


@router.get("/status")
async def status(request: Request):
    """Statuses and live numbers only, for a view that is already drawn."""
    return await architecture.statuses(_routes(request))
