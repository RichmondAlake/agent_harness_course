"""PPA custom-harness appbook: FastAPI application.

Starts the harness in the background so the page loads at once, mounts one
router per chapter, and serves the no-build SPA from the same origin.

    uvicorn backend.main:app --port 8050
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR
from backend.core import runtime, store
from backend.core.workspace import WorkspaceError
from backend.routers import (approvals, architecture, assistant, calendar_intel, connections, context_cost,
                             data_explorer, focus_sessions, governed_meaning, harness, inbox_triage,
                             learning, memory_layer, oracle_window, routines, scorecard, skills, system_one,
                             systems_of_record, teaching, the_loop, weekly_review)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.warm()
    yield
    await runtime.stop()


app = FastAPI(title="PPA custom harness appbook", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def label_activity(request: Request, call_next):
    """Name the route so table activity can say which request caused it."""
    store.set_route(request.url.path)
    try:
        return await call_next(request)
    finally:
        store.set_route(None)


@app.exception_handler(WorkspaceError)
async def workspace_failed(request: Request, exc: WorkspaceError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    return JSONResponse({"detail": f"{type(exc).__name__}: {str(exc)[:300]}"}, status_code=500)


for module in (harness, assistant, architecture, connections, systems_of_record, memory_layer,
               governed_meaning, inbox_triage, calendar_intel, focus_sessions, skills, approvals,
               the_loop, routines, weekly_review, system_one, context_cost, learning, scorecard, teaching,
               data_explorer, oracle_window):
    app.include_router(module.router)

class Frontend(StaticFiles):
    """The pages of the appbook. A browser asks before it reuses a copy, so an edit shows on reload."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", Frontend(directory=str(FRONTEND_DIR), html=True), name="frontend")
