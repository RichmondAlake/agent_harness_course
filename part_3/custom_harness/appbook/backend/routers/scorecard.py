"""Chapter 17: the scorecard and the release gate."""
from fastapi import APIRouter, Depends

from backend.core import scorecard
from backend.routers.deps import ready

router = APIRouter(prefix="/api/scorecard", tags=["scorecard"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    """Every check, computed from live state, and the verdict."""
    return {"chapter": "Scorecard and release gate", **await scorecard.compute()}
