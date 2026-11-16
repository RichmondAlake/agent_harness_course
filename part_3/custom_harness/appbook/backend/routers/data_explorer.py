"""Read-only explorer for every table the harness owns."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.core import explorer, store
from backend.core.events import bus
from backend.routers.deps import ready

router = APIRouter(prefix="/api/data_explorer", tags=["data_explorer"], dependencies=[Depends(ready)])


def _known(table: str) -> str:
    if table not in explorer.listed():
        raise HTTPException(404, "That table is not part of the harness")
    return table


@router.get("/tables")
async def tables():
    found = explorer.tables()
    return {"substrate": store.SUBSTRATE, "access": "read-only", "tables": found,
            "rows": sum(item["row_count"] for item in found),
            "limits": {"rows_per_page": explorer.MAX_ROWS, "rows_per_export": explorer.EXPORT_ROWS,
                       "preview_characters": explorer.PREVIEW}}


@router.get("/tables/{table}/rows")
async def rows(table: str, limit: int = Query(25, ge=1, le=explorer.MAX_ROWS), offset: int = Query(0, ge=0),
               sort: str | None = Query(None, max_length=64),
               direction: Literal["asc", "desc"] = "desc", search: str = Query("", max_length=200)):
    try:
        return explorer.page(_known(table), limit=limit, offset=offset, sort=sort, direction=direction,
                             search=search)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/tables/{table}/rows/{rowid}")
async def record(table: str, rowid: int):
    found = explorer.record(_known(table), rowid)
    if found is None:
        raise HTTPException(404, "No such row")
    return found


@router.get("/tables/{table}/export")
async def export(table: str):
    return JSONResponse(explorer.export(_known(table)), headers={
        "Content-Disposition": f'attachment; filename="{table}.json"'})


@router.get("/activity/recent")
async def recent(limit: int = Query(40, ge=1, le=200)):
    return {"events": bus.recent("activity", limit),
            "note": "Application telemetry from the statements the harness runs. Not a database audit."}
