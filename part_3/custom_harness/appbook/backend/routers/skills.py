"""Chapter 9: skills and progressive disclosure."""
from fastapi import APIRouter, Depends, HTTPException

from backend.core import skills
from backend.routers.deps import ready
from backend.schemas import QueryReq

router = APIRouter(prefix="/api/skills", tags=["skills"], dependencies=[Depends(ready)])


@router.get("/status")
async def status():
    return {"chapter": "Skills", "manifests": skills.manifests(), "live": skills.registry(),
            "token_comparison": skills.token_comparison(None),
            "registry": "ppa_skill_registry holds the live skills, one row each with a version pointer. "
                        "ppa_skill_versions keeps every version ever written."}


@router.post("/match")
async def match(req: QueryReq):
    return skills.disclose(req.query)


@router.get("/{name}")
async def load(name: str):
    found = skills.load(name)
    if found is None:
        raise HTTPException(404, "No such skill")
    return {**found, "token_comparison": skills.token_comparison(name)}
