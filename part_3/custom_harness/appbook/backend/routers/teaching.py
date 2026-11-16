"""The teaching frame of every chapter. It is text, so it is served before the harness is ready."""
from fastapi import APIRouter, HTTPException

from backend.core import teaching

router = APIRouter(prefix="/api/teaching", tags=["teaching"])


@router.get("")
async def everything():
    return teaching.everything()


@router.get("/{chapter}")
async def one(chapter: str):
    found = teaching.frame(chapter)
    if found is None:
        raise HTTPException(404, "No such chapter")
    return found
