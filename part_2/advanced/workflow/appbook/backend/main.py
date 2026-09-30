"""The trip-booking workflow appbook: FastAPI in front of the durable harness."""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent
ADVANCED = BACKEND.parents[2]
sys.path.insert(0, str(ADVANCED))
from shared.appbook import ADVANCED as _ADV, Bus, add_paths, explorer_rows, explorer_tables, load_env  # noqa: E402

add_paths(BACKEND)
load_env()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from shared import oracle  # noqa: E402

app = FastAPI(title="Trip workflow appbook")
bus = Bus()
STATE: dict[str, Any] = {"ready": False, "error": None, "started_at": time.time(), "runs": {}}
PREFIXES = ("TRIP_", "TRIPMEM")


def _install_bus() -> None:
    """Every ledger line the harness writes is also pushed to the browser."""
    from harness import graph, tables
    original = tables.ledger
    if getattr(original, "__wrapped__", None):
        return
    def ledger(trip_id: str, node: str, kind: str, detail: Any) -> None:
        original(trip_id, node, kind, detail)
        bus.publish("ledger", trip_id=trip_id, node=node, kind=kind, detail=detail)
    ledger.__wrapped__ = original  # type: ignore[attr-defined]
    tables.ledger = ledger
    graph.ledger = ledger


def _warm() -> None:
    try:
        oracle.ensure_schema()
        oracle.ensure_embedding_model()
        from harness import graph
        graph.durable_graph()
        _install_bus()
        STATE["ready"] = True
        bus.publish("status", ready=True)
    except Exception as error:  # noqa: BLE001
        STATE["error"] = f"{type(error).__name__}: {str(error)[:300]}"
        bus.publish("status", ready=False, error=STATE["error"])


@app.on_event("startup")
async def startup() -> None:
    bus.loop = asyncio.get_running_loop()
    threading.Thread(target=_warm, name="warm", daemon=True).start()


def ready() -> None:
    if not STATE["ready"]:
        raise HTTPException(503, STATE["error"] or "The harness is still starting.")


def _run(trip_id: str, work) -> None:
    """One harness call at a time per trip, on a thread, with its outcome pushed when it ends."""
    if STATE["runs"].get(trip_id, {}).get("busy"):
        raise HTTPException(409, "This trip is still working on the previous step.")
    STATE["runs"][trip_id] = {"busy": True, "error": None}

    def body():
        from harness import graph
        try:
            work()
            STATE["runs"][trip_id] = {"busy": False, "error": None}
            bus.publish("trip", trip_id=trip_id, outcome=graph.outcome(trip_id))
        except Exception as error:  # noqa: BLE001
            STATE["runs"][trip_id] = {"busy": False, "error": f"{type(error).__name__}: {str(error)[:300]}"}
            bus.publish("trip", trip_id=trip_id, error=STATE["runs"][trip_id]["error"], outcome=graph.outcome(trip_id))
    threading.Thread(target=body, name=f"trip-{trip_id}", daemon=True).start()


def traveller_slug(value: str) -> str:
    """A traveller id as the tables and the memory store key it: lower case, no spaces. 'Richmond Alake' -> 'richmond-alake'."""
    slug = re.sub(r"[^a-z0-9\-_.]+", "-", (value or "").strip().lower()).strip("-.")[:40]
    if not slug:
        raise ValueError("a traveller id is needed")
    return slug


class TripReq(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    traveller_id: str = Field(default="richmond", max_length=120)

    @field_validator("text")
    @classmethod
    def _trim(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("say what the traveller wants")
        return value

    @field_validator("traveller_id")
    @classmethod
    def _slug(cls, value: str) -> str:
        return traveller_slug(value)


class DecisionReq(BaseModel):
    decision: str = Field(pattern=r"^(approve|change|reject)$")
    note: str = ""


class FaultReq(BaseModel):
    component: str = Field(pattern=r"^(flight|hotel|car)$")
    match: str = Field(min_length=1, max_length=200)
    fault: str = Field(default="sold_out", pattern=r"^(sold_out|price_changed|provider_down)$")
    times: int = Field(default=1, ge=1, le=5)


class MemoryReq(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    kind: str = Field(default="preference", pattern=r"^(preference|fact|guideline)$")


@app.get("/api/status")
def status() -> dict:
    from harness import system_one
    from harness.config import CFG
    from harness.llm import USAGE
    info = {"ready": STATE["ready"], "error": STATE["error"], "model": CFG.model,
            "keys": {"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")), "tavily": bool(os.getenv("TAVILY_API_KEY")),
                     "typesafe": bool(os.getenv("TYPESAFE_API_KEY"))},
            "system_one": {"available": system_one.available(), "model": system_one.MODEL, "label": system_one.status()["label"]},
            "database": {"dsn": oracle.ORA.dsn, "user": oracle.ORA.user, "reachable": oracle.reachable()},
            "usage": dict(USAGE), "runs": {k: v for k, v in STATE["runs"].items()}}
    if STATE["ready"]:
        info["database"]["version"] = STATE.setdefault("version", oracle.version())   # the explorer lists tables when opened
    return info


@app.get("/api/events")
async def events():
    return EventSourceResponse(bus.stream())


@app.get("/api/graph")
def graph_shape() -> dict:
    ready()
    from harness import graph as g
    drawn = g.build_graph().get_graph()
    notes = {
        "recall_preferences": "What Oracle Agent Memory knows about this traveller",
        "understand": "The request as a typed object, with questions if a search would be pointless",
        "ask_traveller": "The run ends here until the traveller answers",
        "search_flight": "Tavily search, evidence kept, offers extracted", "search_hotel": "Runs beside the other searches",
        "search_car": "Runs beside the other searches", "join_offers": "Waits for all three; asks when a component has nothing",
        "plan": "One itinerary from the offers, totals computed by the harness",
        "review": "interrupt(): the run stops until the traveller decides", "replan": "The traveller's note goes back into plan",
        "book_flight": "Saga step 1, idempotent", "book_hotel": "Saga step 2", "book_car": "Saga step 3",
        "compensate": "Cancel what was booked; fall back to the next offer; ask again",
        "confirm": "Remember the trip; mark it booked", "close": "Declined, unbookable or waiting for answers"}
    return {"nodes": [{"id": n, "note": notes.get(n, "")} for n in drawn.nodes if not n.startswith("__")],
            "edges": [{"source": e.source, "target": e.target, "conditional": e.conditional}
                      for e in drawn.edges if not e.source.startswith("__") and not e.target.startswith("__")]}


@app.get("/api/trips")
def trips() -> dict:
    ready()
    found = oracle.rows("SELECT trip_id, traveller_id, status, created_at, updated_at, request FROM trip_requests "
                        "ORDER BY created_at DESC FETCH FIRST 30 ROWS ONLY")
    return {"trips": [{**r, "request": str(r["request"])[:200], "busy": STATE["runs"].get(r["trip_id"], {}).get("busy", False)}
                      for r in found]}


@app.post("/api/trips")
def start(req: TripReq) -> dict:
    ready()
    from harness import graph, tables
    trip_id = tables.new_id("TRIP")
    oracle.execute("INSERT INTO trip_requests (trip_id, traveller_id, request, status) VALUES (:1, :2, :3, 'STARTED')",
                   [trip_id, req.traveller_id, req.text])
    _run(trip_id, lambda: graph.start_trip(req.text, req.traveller_id, trip_id=trip_id))
    return {"trip_id": trip_id, "traveller_id": req.traveller_id, "status": "running"}


@app.get("/api/system_one/status")
def system_one_status() -> dict:
    ready()
    from harness import system_one
    return {**system_one.status(), "decisions_made_for": [
        {"decision": "Which memories bear on this request?", "question": "noul, one for each memory",
         "used_by": "recall_preferences", "fallback": "every memory is used"},
        {"decision": "Which search results are worth reading, and which give orders?", "question": "two noul for each result",
         "used_by": "the three searches", "fallback": "every result is read"},
        {"decision": "Does each chosen offer honour each preference?", "question": "choice for each pair",
         "used_by": "plan", "fallback": "no checks are made"},
        {"decision": "May a fallback be booked on the approval already given?", "question": "one noul",
         "used_by": "compensate", "fallback": "the traveller is always asked"}]}


@app.get("/api/trips/{trip_id}/decisions")
def trip_decisions(trip_id: str) -> dict:
    ready()
    from harness import system_one
    return {"trip_id": trip_id, "decisions": system_one.decisions(trip_id, limit=100)}


@app.get("/api/trips/{trip_id}")
def trip(trip_id: str) -> dict:
    ready()
    from harness import graph, tables
    out = graph.outcome(trip_id)
    run = STATE["runs"].get(trip_id, {})
    return {**out, "busy": run.get("busy", False), "error": run.get("error"), "ledger": tables.trip_ledger(trip_id),
            "evidence": oracle.rows("SELECT component, query, url, title, score, relevance, attack, kept FROM trip_evidence "
                                    "WHERE trip_id = :t ORDER BY fetched_at", {"t": trip_id}),
            "offers": oracle.rows("SELECT offer_id, component, provider, summary, price, currency, price_gbp, confidence, "
                                  "evidence_id FROM trip_offers WHERE trip_id = :t ORDER BY component, price_gbp", {"t": trip_id})}


@app.post("/api/trips/{trip_id}/decide")
def decide(trip_id: str, req: DecisionReq) -> dict:
    ready()
    from harness import graph
    if not graph.outcome(trip_id)["waiting_for_traveller"]:
        raise HTTPException(409, "This trip is not waiting for a decision.")
    _run(trip_id, lambda: graph.resume_trip(trip_id, req.decision, req.note))
    return {"trip_id": trip_id, "status": "running"}


@app.post("/api/trips/{trip_id}/continue")
def resume(trip_id: str) -> dict:
    ready()
    from harness import graph
    _run(trip_id, lambda: graph.continue_trip(trip_id))
    return {"trip_id": trip_id, "status": "running"}


@app.post("/api/faults")
def fault(req: FaultReq) -> dict:
    ready()
    from harness import bookings
    return {"fault_id": bookings.add_fault(req.component, req.match, req.fault, req.times)}


@app.get("/api/faults")
def faults() -> dict:
    ready()
    return {"faults": oracle.rows("SELECT fault_id, component, match, fault, remaining FROM trip_provider_faults")}


def _traveller(value: str) -> str:
    try:
        return traveller_slug(value)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/memory/{traveller_id}")
def memory(traveller_id: str, query: str = "travel preferences") -> dict:
    ready()
    from harness import memory as mem
    traveller_id = _traveller(traveller_id)
    return {"traveller_id": traveller_id, "recalled": mem.recall(traveller_id, query, limit=12)}


@app.post("/api/memory/{traveller_id}")
def remember(traveller_id: str, req: MemoryReq) -> dict:
    ready()
    from harness import memory as mem
    return mem.remember(_traveller(traveller_id), req.content, req.kind)


@app.delete("/api/memory/{traveller_id}")
def forget(traveller_id: str) -> dict:
    ready()
    from harness import memory as mem
    traveller_id = _traveller(traveller_id)
    mem.forget_traveller(traveller_id)
    return {"forgotten": traveller_id}


@app.post("/api/crash_demo")
def crash_demo() -> dict:
    """The two-process proof, run as a subprocess; its lines are streamed as events."""
    ready()
    if STATE.get("crash_busy"):
        raise HTTPException(409, "The crash demonstration is already running.")
    STATE["crash_busy"] = True
    from harness import tables
    trip_id = tables.new_id("TRIP-crash")

    def body():
        script = ADVANCED / "scripts" / "trip_crash_and_resume.py"
        with subprocess.Popen([sys.executable, str(script), trip_id], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, env={**os.environ}) as proc:
            for line in proc.stdout:
                if line.strip() and not line.startswith(("INFO", "WARNING")):
                    bus.publish("crash", trip_id=trip_id, line=line.rstrip())
        STATE["crash_busy"] = False
        bus.publish("crash", trip_id=trip_id, done=True, exit_code=proc.returncode)
    threading.Thread(target=body, name="crash-demo", daemon=True).start()
    return {"trip_id": trip_id, "status": "running"}


@app.get("/api/explorer/tables")
def tables_listed() -> dict:
    ready()
    return {"tables": explorer_tables(PREFIXES)}


@app.get("/api/explorer/tables/{name}/rows")
def table_rows(name: str, limit: int = 50, offset: int = 0, search: str = "") -> dict:
    ready()
    try:
        return explorer_rows(name, PREFIXES, limit, offset, search)
    except KeyError:
        raise HTTPException(404, "That table is not part of the harness")


@app.post("/api/reset")
def reset() -> dict:
    ready()
    from harness import tables
    tables.reset_trip_tables()
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        oracle.execute(f"DELETE FROM {table} WHERE thread_id LIKE 'TRIP-%'")
    STATE["runs"] = {}
    bus.publish("status", ready=True, reset=True)
    return {"reset": True}


@app.exception_handler(Exception)
async def unexpected(request, exc: Exception):
    return JSONResponse({"detail": f"{type(exc).__name__}: {str(exc)[:300]}"}, status_code=500)


class Frontend(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/shared", Frontend(directory=str(ADVANCED / "shared" / "frontend")), name="shared")
app.mount("/", Frontend(directory=str(BACKEND.parent / "frontend"), html=True), name="frontend")
