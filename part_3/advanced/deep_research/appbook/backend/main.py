"""The survey-paper appbook: FastAPI in front of the deep-research harness."""
from __future__ import annotations

import re

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
from shared.appbook import Bus, add_paths, explorer_rows, explorer_tables, load_env  # noqa: E402

add_paths(BACKEND)
load_env()
os.environ.setdefault("SURVEY_OUTPUT_DIR", str(BACKEND.parents[1] / "output"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from shared import oracle  # noqa: E402

app = FastAPI(title="Survey paper appbook")

import labs  # noqa: E402

app.include_router(labs.router)
bus = Bus()
STATE: dict[str, Any] = {"ready": False, "error": None, "runs": {}}
PREFIXES = ("SURVEY_",)


STEP_OF = {"scope": "scope", "research": "gather", "compact": "gather", "reflect": "reflect", "taxonomy": "organise",
           "section": "write", "claims": "write", "repair": "write", "review": "review", "abstract": "assemble"}


def _brief_result(name: str, shown: str) -> str:
    """One line on what a tool call returned, for the trace."""
    lines = [line for line in shown.splitlines() if line.strip()]
    if name == "search_web" and lines and " | " in lines[0]:
        titles = [line.split(" | ")[1] for line in lines if line.count(" | ") >= 2]
        return f"{len(titles)} new works: " + "; ".join(title[:70] for title in titles[:3]) + (" …" if len(titles) > 3 else "")
    if name == "read_page" and len(lines) > 1 and lines[1].startswith("Stored in full"):
        return f"{lines[0][:120]} · {lines[1].split('. ')[0].lower()}"
    if name in ("load_skill", "recall") and len(shown) > 160:
        return f"{len(shown):,} characters returned"
    return (lines[0] if lines else "")[:200]


def _install_bus() -> None:
    """The appbook listens to the harness without changing it: every ledger entry, model call and tool call
    is announced to the open pages, and tool calls are kept in a table of the appbook's own."""
    from harness import budget, graph, llm, research, tables
    original = tables.ledger
    if getattr(original, "__wrapped__", None):
        return
    oracle.ddl("""CREATE TABLE survey_tool_calls (
        call_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, section_key VARCHAR2(60), round NUMBER,
        name VARCHAR2(40) NOT NULL, arguments VARCHAR2(4000), outcome VARCHAR2(1000), result_chars NUMBER, seconds NUMBER,
        at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP)""")

    def ledger(paper_id: str, node: str, kind: str, detail: Any) -> None:
        original(paper_id, node, kind, detail)
        bus.publish("ledger", paper_id=paper_id, node=node, kind=kind, detail=detail)
    ledger.__wrapped__ = original  # type: ignore[attr-defined]
    for module in (tables, graph, research, budget):
        module.ledger = ledger

    record = llm.record_call

    def record_call(paper_id: str, kind: str, section: str | None, bill: dict, seconds: float) -> None:
        record(paper_id, kind, section, bill, seconds)
        bus.publish("trace", paper_id=paper_id)
    llm.record_call = record_call

    run = research.run_tool

    def run_tool(work: dict, name: str, args: dict) -> str:
        started = time.perf_counter()
        shown = run(work, name, args)
        oracle.execute("INSERT INTO survey_tool_calls (call_id, paper_id, section_key, round, name, arguments, outcome, "
                       "result_chars, seconds) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)",
                       [tables.new_id("T"), work["paper_id"], work["section"]["key"], work["round"], name,
                        json.dumps(args, default=str)[:4000], _brief_result(name, shown)[:1000], len(shown),
                        round(time.perf_counter() - started, 2)])
        bus.publish("trace", paper_id=work["paper_id"])
        return shown
    research.run_tool = run_tool


def _warm() -> None:
    try:
        oracle.start_database()            # starts the container when it is not answering; creates it the first time
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


def _run(paper_id: str, work) -> None:
    if STATE["runs"].get(paper_id, {}).get("busy"):
        raise HTTPException(409, "This paper is still working on the previous step.")
    STATE["runs"][paper_id] = {"busy": True, "error": None, "since": time.time()}

    def body():
        from harness import graph
        try:
            work()
            STATE["runs"][paper_id] = {"busy": False, "error": None}
            bus.publish("paper", paper_id=paper_id, outcome=_brief(graph.outcome(paper_id)))
        except Exception as error:  # noqa: BLE001
            STATE["runs"][paper_id] = {"busy": False, "error": f"{type(error).__name__}: {str(error)[:300]}"}
            bus.publish("paper", paper_id=paper_id, error=STATE["runs"][paper_id]["error"])
    threading.Thread(target=body, name=f"paper-{paper_id}", daemon=True).start()


def _light(out: dict) -> dict:
    """The outcome without the paper's full text: the page reads that from paper.md."""
    if out.get("paper"):
        out = {**out, "paper": {k: v for k, v in out["paper"].items() if k != "markdown"}}
    return out


def _brief(out: dict) -> dict:
    return {k: v for k, v in _light(out).items() if k not in ("log", "taxonomy")}


class PaperReq(BaseModel):
    subject: str = Field(min_length=3, max_length=300)
    audience: str = Field(default="researchers and engineers building agent systems", max_length=200)


class DecisionReq(BaseModel):
    decision: str = Field(pattern=r"^(approve|revise|reject|override)$")
    note: str = ""
    cut_off: bool = False              # the durability test: stop this run inside `organise`, before its checkpoint


class QueryReq(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=6, ge=1, le=20)


@app.get("/api/status")
def status() -> dict:
    from harness.config import CFG
    from harness.budget import usage
    info = {"ready": STATE["ready"], "error": STATE["error"], "model": CFG.model,
            "limits": {"sections": CFG.sections, "sources_per_section": CFG.sources_per_section,
                       "min_words": CFG.min_words_per_section, "min_citations": CFG.min_citations_per_section,
                       "max_rounds": CFG.max_rounds},
            "keys": {"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")), "tavily": bool(os.getenv("TAVILY_API_KEY"))},
            "database": {"dsn": oracle.ORA.dsn, "user": oracle.ORA.user, "reachable": oracle.reachable()},
            "usage": usage(), "runs": dict(STATE["runs"])}
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
    notes = {"scope": "Research questions, inclusion criteria, an outline with queries per section",
             "outline_review": "interrupt(): nothing is read before a person approves the plan",
             "rescope": "The reader's note goes back into scope", "reflect": "The model says which sections are thin; the harness decides whether to search again, within rounds and budget", "gather": "One researcher per section: a tool loop that searches, reads pages, loads skills and takes notes, with offloading and compaction",
             "tally": "Where the researchers join: counts the library and the notes, calls no model",
             "organise": "Framework, comparison table and open questions from the notes; reused if already saved",
             "write": "One task per section: evidence pack, then a typed draft citing only its pack",
             "review": "Referee pass by the model, plus the harness's own rules", "assemble": "Numbered citations, references, abstract, how it was made",
             "publication_review": "interrupt(): the paper waits for a person", "publish": "The paper as a Markdown file; what the referee found missing is remembered", "close": "Declined"}
    return {"nodes": [{"id": n, "note": notes.get(n, "")} for n in drawn.nodes if not n.startswith("__")],
            "edges": [{"source": e.source, "target": e.target, "conditional": e.conditional}
                      for e in drawn.edges if not e.source.startswith("__") and not e.target.startswith("__")]}


@app.get("/api/papers")
def papers() -> dict:
    ready()
    found = oracle.rows("SELECT paper_id, subject, title, status, created_at, updated_at FROM survey_papers "
                        "ORDER BY created_at DESC FETCH FIRST 30 ROWS ONLY")
    return {"papers": [{**r, "busy": STATE["runs"].get(r["paper_id"], {}).get("busy", False)} for r in found]}


@app.post("/api/papers")
def start(req: PaperReq) -> dict:
    ready()
    from harness import graph, tables
    paper_id = tables.new_id("PAPER")
    oracle.execute("INSERT INTO survey_papers (paper_id, subject, brief, status) VALUES (:1, :2, :3, 'STARTED')",
                   [paper_id, req.subject, json.dumps({"audience": req.audience})])
    _run(paper_id, lambda: graph.start_paper(req.subject, req.audience, paper_id=paper_id))
    return {"paper_id": paper_id, "status": "running"}


@app.get("/api/papers/{paper_id}")
def paper(paper_id: str) -> dict:
    ready()
    from harness import graph, tables
    out = _light(graph.outcome(paper_id))
    run = STATE["runs"].get(paper_id, {})
    return {**out, "busy": run.get("busy", False), "error": run.get("error"), "ledger": tables.paper_ledger(paper_id),
            "sources_by_section": oracle.rows("SELECT section_key, COUNT(*) AS n FROM survey_sources WHERE paper_id = :p "
                                              "GROUP BY section_key ORDER BY 1", {"p": paper_id}),
            "reviews": oracle.rows("SELECT round, verdict, findings FROM survey_reviews WHERE paper_id = :p ORDER BY at",
                                   {"p": paper_id})}


@app.get("/api/papers/{paper_id}/trace")
def trace(paper_id: str) -> dict:
    """Everything that happened for one paper, in order: steps and decisions from the ledger, every model call,
    and every tool call a researcher made. All three are timed by the database, so they sort together."""
    ready()
    events = []
    for row in oracle.rows("SELECT node, kind, detail, at FROM survey_ledger WHERE paper_id = :p", {"p": paper_id}):
        text = row["detail"] or ""
        events.append({"at": row["at"], "type": "budget" if row["kind"] == "budget" else "step", "step": row["node"],
                       "kind": row["kind"], "detail": json.loads(text) if text[:1] in "{[" else text})
    for row in oracle.rows("""SELECT kind, section_key, input_tokens, cache_write_tokens, cache_read_tokens, output_tokens,
                                     cost_usd, seconds, at FROM survey_model_calls WHERE paper_id = :p""", {"p": paper_id}):
        events.append({"at": row["at"], "type": "model", "step": STEP_OF.get(row["kind"], row["kind"]), "kind": row["kind"],
                       "section": row["section_key"], "usd": row["cost_usd"], "seconds": row["seconds"],
                       "tokens": {"fresh": row["input_tokens"], "cache_write": row["cache_write_tokens"],
                                  "cache_read": row["cache_read_tokens"], "output": row["output_tokens"]}})
    for row in oracle.rows("""SELECT section_key, round, name, arguments, outcome, result_chars, seconds, at
                              FROM survey_tool_calls WHERE paper_id = :p""", {"p": paper_id}):
        events.append({"at": row["at"], "type": "tool", "step": "gather", "kind": row["name"], "section": row["section_key"],
                       "round": row["round"], "arguments": json.loads(row["arguments"] or "{}"), "outcome": row["outcome"],
                       "result_chars": row["result_chars"], "seconds": row["seconds"]})
    events.sort(key=lambda event: event["at"])
    run = STATE["runs"].get(paper_id, {})
    return {"paper_id": paper_id, "busy": run.get("busy", False), "error": run.get("error"), "events": events}


@app.get("/api/progress")
def progress(paper_id: str = "") -> dict:
    """The paper to show on every page: the one that is working, or else the selected one if it waits or has stopped."""
    ready()
    from harness import graph
    from harness.budget import usage
    from harness.config import CFG
    working = sorted((p for p, run in STATE["runs"].items() if run.get("busy")), key=lambda p: STATE["runs"][p].get("since", 0))
    chosen = working[-1] if working else paper_id
    found = oracle.rows("SELECT title, subject FROM survey_papers WHERE paper_id = :p", {"p": chosen}) if chosen else []
    if not found:
        return {"paper": None}
    run = STATE["runs"].get(chosen, {})
    latest = oracle.rows("""SELECT * FROM (
          SELECT 'step' AS type, node AS step, kind, CAST(NULL AS VARCHAR2(60)) AS section_key, at FROM survey_ledger WHERE paper_id = :p
          UNION ALL SELECT 'model', kind, kind, section_key, at FROM survey_model_calls WHERE paper_id = :p
          UNION ALL SELECT 'tool', 'gather', name, section_key, at FROM survey_tool_calls WHERE paper_id = :p)
        ORDER BY at DESC FETCH FIRST 1 ROWS ONLY""", {"p": chosen})
    last = latest[0] if latest else None
    if last and last["type"] == "model":
        last["step"] = STEP_OF.get(last["kind"], last["kind"])
    out = {"status": "working", "next": [], "waiting_for_person": False, "resume_from": []} if run.get("busy") else graph.outcome(chosen)
    spent = usage(chosen)
    return {"paper": {"paper_id": chosen, "title": found[0]["title"] or found[0]["subject"], "busy": bool(run.get("busy")),
                      "error": run.get("error"), "status": out["status"], "waiting_for_person": out["waiting_for_person"],
                      "next": out["next"], "resume_from": out["resume_from"], "last": last,
                      "seconds": round(time.time() - run["since"]) if run.get("busy") and run.get("since") else None,
                      "calls": spent["calls"], "usd": spent["cost_usd"], "budget_usd": CFG.budget_usd,
                      "tool_calls": oracle.rows("SELECT COUNT(*) AS n FROM survey_tool_calls WHERE paper_id = :p", {"p": chosen})[0]["n"],
                      "sources": oracle.rows("SELECT COUNT(*) AS n FROM survey_sources WHERE paper_id = :p", {"p": chosen})[0]["n"]}}


@app.get("/api/papers/{paper_id}/sources")
def sources(paper_id: str) -> dict:
    ready()
    from harness.evidence import sources_for
    return {"sources": sources_for(paper_id)}


@app.post("/api/papers/{paper_id}/similar")
def similar(paper_id: str, req: QueryReq) -> dict:
    ready()
    from harness.evidence import similar_sources
    return {"query": req.query, "sources": similar_sources(paper_id, req.query, req.limit)}


@app.get("/api/papers/{paper_id}/notes")
def notes(paper_id: str, section: str | None = None) -> dict:
    ready()
    from harness.reading import notes_for
    return {"notes": notes_for(paper_id, section)}


@app.get("/api/papers/{paper_id}/sections")
def sections(paper_id: str) -> dict:
    ready()
    from harness.writing import drafts
    return {"sections": drafts(paper_id)}


@app.get("/api/papers/{paper_id}/paper.md", response_class=PlainTextResponse)
def paper_markdown(paper_id: str) -> str:
    ready()
    found = oracle.rows("SELECT markdown FROM survey_papers WHERE paper_id = :p", {"p": paper_id})
    if not found or not found[0]["markdown"]:
        raise HTTPException(404, "The paper is not assembled yet.")
    return found[0]["markdown"]


@app.get("/api/papers/{paper_id}/paper.html", response_class=HTMLResponse)
def paper_html(paper_id: str) -> str:
    ready()
    found = oracle.rows("SELECT markdown, title FROM survey_papers WHERE paper_id = :p", {"p": paper_id})
    if not found or not found[0]["markdown"]:
        raise HTTPException(404, "The paper is not assembled yet.")
    return to_html(found[0]["markdown"], found[0]["title"] or paper_id)


@app.post("/api/papers/{paper_id}/decide")
def decide(paper_id: str, req: DecisionReq) -> dict:
    ready()
    from harness import graph
    if not graph.outcome(paper_id)["waiting_for_person"]:
        raise HTTPException(409, "This paper is not waiting for a decision.")
    def work():
        import dataclasses
        normal = graph.CFG
        if req.cut_off:
            graph.CFG = dataclasses.replace(normal, crash_after="organise")
        try:
            graph.resume_paper(paper_id, req.decision, req.note)
        except graph.Crashed:
            pass                      # the run now shows as interrupted, and Continue picks it up
        finally:
            graph.CFG = normal
    _run(paper_id, work)
    return {"paper_id": paper_id, "status": "running"}


@app.get("/api/papers/{paper_id}/release")
def release(paper_id: str) -> dict:
    """The release check for a paper as it stands now: counted facts only, no model call."""
    ready()
    import json as _json
    from harness.writing import release_check
    found = oracle.rows("SELECT outline FROM survey_papers WHERE paper_id = :p", {"p": paper_id})
    if not found or not found[0]["outline"]:
        raise HTTPException(404, "This paper has no outline yet.")
    reviews = oracle.rows("SELECT findings FROM survey_reviews WHERE paper_id = :p ORDER BY at DESC FETCH FIRST 1 ROWS ONLY",
                          {"p": paper_id})
    return release_check(paper_id, _json.loads(found[0]["outline"]), _json.loads(reviews[0]["findings"]) if reviews else {})


@app.post("/api/papers/{paper_id}/continue")
def resume(paper_id: str) -> dict:
    ready()
    from harness import graph
    _run(paper_id, lambda: graph.continue_paper(paper_id))
    return {"paper_id": paper_id, "status": "running"}


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
    tables.reset_survey_tables()
    oracle.execute("DELETE FROM survey_tool_calls")
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        oracle.execute(f"DELETE FROM {table} WHERE thread_id LIKE 'PAPER-%'")
    STATE["runs"] = {}
    return {"reset": True}


@app.exception_handler(Exception)
async def unexpected(request, exc: Exception):
    return JSONResponse({"detail": f"{type(exc).__name__}: {str(exc)[:300]}"}, status_code=500)


class Frontend(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/shared", Frontend(directory=str(BACKEND.parent / "frontend" / "shared")), name="shared")

def to_html(markdown: str, title: str) -> str:
    """A printable page. Headings, paragraphs, lists, tables, emphasis and links are enough."""
    import html as html_lib
    lines = markdown.split("\n")
    out, in_list, in_table = [], False, False
    inline = lambda t: re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>",
                              re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>",
                                     re.sub(r"`(.+?)`", r"<code>\1</code>",
                                            re.sub(r"(https?://[^\s)]+)", r'<a href="\1">\1</a>', html_lib.escape(t)))))
    for line in lines:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>"); in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>"); in_table = False
        if re.match(r"^(\d+\.|[-*]) ", line):
            if not in_list:
                out.append("<ul>" if line[0] in "-*" else "<ol>"); in_list = line[0]
            out.append(f"<li>{inline(re.sub(r'^(\\d+\\.|[-*]) ', '', line))}</li>")
            continue
        if in_list:
            out.append("</ul>" if in_list in "-*" else "</ol>"); in_list = False
        heading = re.match(r"^(#{1,4}) (.*)", line)
        if heading:
            out.append(f"<h{len(heading[1])}>{inline(heading[2])}</h{len(heading[1])}>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>" if in_list in "-*" else "</ol>")
    if in_table:
        out.append("</table>")
    style = ("body{font-family:Georgia,serif;max-width:52em;margin:2em auto;padding:0 1em;line-height:1.55;color:#1c1c1c}"
             "h1{font-size:1.8em}h2{margin-top:2em;border-bottom:1px solid #ccc}table{border-collapse:collapse;margin:1em 0;"
             "font-size:.9em}th,td{border:1px solid #bbb;padding:.35em .6em;vertical-align:top}th{background:#f2f2f2}"
             "code{font-family:Menlo,monospace;font-size:.9em}@media print{body{max-width:none;margin:0}}")
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{html_lib.escape(title)}</title>"
            f"<style>{style}</style></head><body>{''.join(out)}</body></html>")


app.mount("/", Frontend(directory=str(BACKEND.parent / "frontend"), html=True), name="frontend")
