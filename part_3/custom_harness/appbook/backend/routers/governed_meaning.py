"""Chapter 5: governed meaning."""
from fastapi import APIRouter, Depends

from backend.core import clock, governed
from backend.routers.deps import ready
from backend.schemas import QuestionReq

router = APIRouter(prefix="/api/governed_meaning", tags=["governed_meaning"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    return {"chapter": "Governed meaning", "definitions": governed.definitions(),
            "questions": governed.QUESTIONS, "clock": clock.status(),
            "teaching_point": "The model chooses what to do. The policy decides what is true."}


@router.post("/compare")
async def compare(req: QuestionReq):
    return await governed.compare(req.question)
