"""The data explorer's window on the notebook's Oracle AI Database. Read-only."""
import asyncio

from fastapi import APIRouter, HTTPException, Query

from backend.core import oracle_window

router = APIRouter(prefix="/api/oracle", tags=["oracle"])


def _not_reachable(reason: str) -> dict:
    where = oracle_window.status()
    return {"reachable": False, "reason": reason, **where,
            "detail": f"Oracle AI Database cannot be reached at {where['dsn']}. {oracle_window.HOW}"}


@router.get("")
async def overview():
    """What the notebook's harness left in the database. Answers 200 when there is no database."""
    try:
        found = await asyncio.to_thread(oracle_window.catalogue)
    except oracle_window.NotReachable as exc:
        return _not_reachable(str(exc))
    except oracle_window.Busy as exc:
        raise HTTPException(503, str(exc)) from exc
    return {**found, **oracle_window.status()}


@router.get("/objects/{name}")
async def one(name: str, limit: int = Query(oracle_window.ROWS, ge=1, le=oracle_window.ROWS)):
    """Columns, row count and the newest rows of one table or view."""
    import oracledb

    try:
        return await asyncio.to_thread(oracle_window.read, name, limit)
    except oracle_window.NotReachable as exc:
        return _not_reachable(str(exc))
    except oracle_window.UnknownObject as exc:
        raise HTTPException(404, "No table or view of that name is in the data dictionary") from exc
    except oracle_window.Busy as exc:
        raise HTTPException(503, str(exc)) from exc
    except oracledb.Error as exc:
        if oracle_window._timed_out(exc):
            raise HTTPException(503, oracle_window.BUSY) from exc
        raise HTTPException(502, f"The database refused the read: {str(exc).splitlines()[0][:200]}") from exc
