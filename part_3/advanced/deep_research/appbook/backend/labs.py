"""Try one component of the harness at a time.

Every route here calls the same function the full run calls, on a small practice
paper of its own, so what a lab spends and stores is kept apart from real papers.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared import oracle

router = APIRouter(prefix="/api/lab")
LAB_PAPER = "PAPER-lab"
LAB_READER = "reader-lab"
LAB: dict[str, Any] = {"subject": "agent harness engineering",
                       "section": {"key": "lab", "kind": "thematic", "position": 1,
                                   "title": "Context engineering and memory",
                                   "purpose": "How agent harnesses decide what stays in the context window and what is kept as memory."},
                       "framework": None, "work": None}
CACHE_TEXT = ("An agent harness is the program around a language model. It assembles the context, exposes tools, runs "
              "the model's tool calls, keeps state and memory, enforces limits and decides when a person must agree. ") * 60


class Text(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Search(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    scholarly: bool = True


class Brief(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=3)
    missing: list[str] = Field(default_factory=list, max_length=6)


class Memory(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    kind: str = Field(default="preference", pattern=r"^(preference|guideline|fact)$")
    replaces: str | None = None


class Quote(BaseModel):
    quote: str = Field(min_length=1, max_length=600)
    page: str = Field(min_length=1, max_length=60_000)


class Budget(BaseModel):
    budget_usd: float = Field(ge=0, le=100)
    asked: int = Field(ge=1, le=20)
    work: str = Field(pattern=r"^(follow_up|revise)$")
    paper_id: str | None = None


class ToolCall(BaseModel):
    name: str = Field(pattern=r"^(search_web|read_page|load_skill|take_note|recall|finish)$")
    args: dict


class Scope(BaseModel):
    subject: str = Field(min_length=3, max_length=300)
    section_title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=400)


def lab_paper() -> str:
    if not oracle.rows("SELECT 1 FROM survey_papers WHERE paper_id = :p", {"p": LAB_PAPER}):
        oracle.execute("INSERT INTO survey_papers (paper_id, subject, status) VALUES (:1, :2, 'LAB')", [LAB_PAPER, LAB["subject"]])
    return LAB_PAPER


def calls(limit: int = 4) -> list[dict]:
    """The newest priced rows of the lab, newest last."""
    found = oracle.rows("""SELECT kind, input_tokens AS fresh, cache_write_tokens AS cache_write, cache_read_tokens AS cache_read,
                                  output_tokens AS output, ROUND(cost_usd, 4) AS usd, seconds FROM survey_model_calls
                           WHERE paper_id = :p ORDER BY at DESC FETCH FIRST :n ROWS ONLY""", {"p": LAB_PAPER, "n": limit})
    return found[::-1]


@router.get("")
def state() -> dict:
    from harness.budget import usage
    from harness.evidence import sources_for
    from harness.reading import notes_for
    paper = lab_paper()
    return {"paper_id": paper, "reader": LAB_READER, "subject": LAB["subject"], "section": LAB["section"],
            "sources": sources_for(paper), "notes": len(notes_for(paper)),
            "has_framework": LAB["framework"] is not None, "usage": usage(paper)}


@router.post("/reset")
def reset(req: Scope) -> dict:
    """Empty the practice paper and point it at a subject and one section."""
    for table in ("survey_sources", "survey_notes", "survey_sections", "survey_claims", "survey_model_calls", "survey_ledger"):
        oracle.execute(f"DELETE FROM {table} WHERE paper_id = :p", {"p": LAB_PAPER})
    LAB.update(subject=req.subject, framework=None, work=None,
               section={**LAB["section"], "title": req.section_title, "purpose": req.purpose})
    return state()


# ── foundation and state store ────────────────────────────────────────────────

@router.post("/embed")
def embed(req: Text) -> dict:
    started = time.perf_counter()
    vector = list(oracle.embedding(req.text))
    return {"dimensions": len(vector), "first": [round(v, 4) for v in vector[:8]],
            "seconds": round(time.perf_counter() - started, 3), "model": oracle.ORA.embed_model}


@router.post("/ledger")
def write_ledger(req: Text) -> dict:
    from harness.tables import ledger, paper_ledger
    ledger(lab_paper(), "lab", "note", req.text)
    return {"ledger": paper_ledger(LAB_PAPER)[-6:]}


# ── model gateway and cost control ────────────────────────────────────────────

@router.post("/ask")
def ask(req: Text) -> dict:
    from harness.llm import ask_typed
    schema = {"type": "object", "properties": {"answer": {"type": "string"},
                                               "confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
              "required": ["answer", "confidence"]}
    answer = ask_typed("Answer in two sentences at most, and say how confident you are.", req.text, "scope", schema,
                       max_tokens=500, effort="low", paper_id=lab_paper())
    return {"answer": answer, "schema": schema, "call": calls(1)}


@router.post("/cache")
def cache() -> dict:
    """Two calls that begin with the same long text: the first writes it to the cache, the second reads it."""
    from harness.llm import ask_typed
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    answers = [ask_typed("Answer in one sentence.", question, "scope", schema, max_tokens=200, effort="low",
                         paper_id=lab_paper(), shared=CACHE_TEXT)["answer"]
               for question in ("What does a harness do with tool calls?", "When does a harness ask a person?")]
    return {"answers": answers, "calls": calls(2), "shared_chars": len(CACHE_TEXT)}


@router.post("/budget")
def budget(req: Budget) -> dict:
    """What `grant` would allow: the same sum, shown with its parts, and nothing written."""
    from harness.budget import SECTION_CALLS, estimate, usage
    from harness.config import CFG
    paper = req.paper_id or lab_paper()
    sections = len(oracle.rows("SELECT 1 FROM survey_sections WHERE paper_id = :p", {"p": paper})) or CFG.sections + 6
    if req.work == "follow_up":
        each = {"notes": CFG.sources_per_section / CFG.read_batch}
        reserve = {"taxonomy": 1, "review": 1, "abstract": 1, "reflect": 1,
                   **{kind: n * sections for kind, n in SECTION_CALLS.items()}}
    else:
        each, reserve = {**SECTION_CALLS, "notes": 1}, {"review": 1, "abstract": 1}
    spent, kept_back, one = usage(paper)["cost_usd"], estimate(paper, reserve), estimate(paper, each)
    room = req.budget_usd - spent - kept_back
    return {"paper_id": paper, "spent_usd": round(spent, 2), "reserved_usd": round(kept_back, 2), "each_usd": round(one, 3),
            "room_usd": round(room, 2), "asked": req.asked, "granted": max(0, min(req.asked, int(room // one))) if one else req.asked}


# ── evidence store ────────────────────────────────────────────────────────────

@router.post("/search")
def search(req: Search) -> dict:
    from harness.evidence import canonical, clean_title, search_web
    started = time.perf_counter()
    found = search_web(req.query, scholarly=req.scholarly)
    return {"seconds": round(time.perf_counter() - started, 2),
            "results": [{**r, "title": clean_title(r["title"]), "key": canonical(r["url"]), "snippet": r["snippet"][:300]} for r in found]}


@router.post("/fetch")
def fetch(req: Text) -> dict:
    from harness.evidence import read_pages
    pages = read_pages([req.text.strip()])
    text = next(iter(pages.values()), "")
    if not text:
        raise HTTPException(404, "The search service returned no text for that address.")
    return {"chars": len(text), "start": text[:1500]}


@router.post("/similar")
def similar(req: Text) -> dict:
    from harness.evidence import similar_sources
    return {"sources": similar_sources(lab_paper(), req.text, limit=5)}


# ── vocabulary and skills ─────────────────────────────────────────────────────

@router.post("/vocabulary")
def vocabulary(req: Text) -> dict:
    """The terms that bear on a text, and the block a prompt would carry for it."""
    from harness.semantics import term_slips, vocabulary_for, vocabulary_text
    terms = vocabulary_for(req.text, limit=6)
    return {"terms": terms, "prompt_text": vocabulary_text(terms), "slips": term_slips(req.text)}


@router.post("/skills")
def skills(req: Text) -> dict:
    """The first level of disclosure: the skills nearest to a task, and the manifest a prompt would carry."""
    from harness.skills import skill_manifest, skills_for
    nearest = skills_for(req.text, limit=4)
    return {"skills": nearest, "manifest": skill_manifest(nearest)}


@router.get("/skills/{name}")
def skill(name: str) -> dict:
    """The second level of disclosure: one skill's full procedure."""
    from harness.skills import load_skill
    body = load_skill(name)
    if body is None:
        raise HTTPException(404, "No skill has that name.")
    return {"name": name, "body": body, "chars": len(body)}


# ── tools, context management and the research loop ───────────────────────────

def lab_work() -> dict:
    """The state one researcher carries between tool calls: the links its searches returned, the pages it has read."""
    if LAB["work"] is None:
        rounds = oracle.rows("SELECT NVL(MAX(round), 0) AS r FROM survey_sources WHERE paper_id = :p", {"p": lab_paper()})[0]["r"]
        LAB["work"] = {"paper_id": LAB_PAPER, "section": LAB["section"], "round": int(rounds) + 1, "found": {}, "kept": [],
                       "searches": [], "skills": [], "notes": 0, "report": None}
    return LAB["work"]


@router.get("/tools")
def tools() -> dict:
    """The tools as the model sees them: a name, when to use it, and the exact shape of its arguments."""
    from harness.config import CFG
    from harness.research import RESEARCH_TOOLS, RESEARCHER
    return {"graph": [{"from": e.source.strip("_"), "to": e.target.strip("_"), "chosen_at_run_time": e.conditional}
                      for e in RESEARCHER.get_graph().edges],
            "tools": [{"name": t["name"], "description": t["description"], "arguments": list(t["input_schema"]["properties"])}
                      for t in RESEARCH_TOOLS],
            "limits": {"pages per section": CFG.sources_per_section, "turns": CFG.max_research_turns,
                       "characters of a page shown": CFG.page_digest_chars, "conversation tokens before a summary": CFG.compact_at_tokens}}


@router.post("/tool")
def tool_call(req: ToolCall) -> dict:
    """Run one tool call by hand, exactly as the harness runs it for the model. No model is called."""
    from harness.research import RESEARCH_TOOLS, run_tool
    wanted = next(t for t in RESEARCH_TOOLS if t["name"] == req.name)["input_schema"]["properties"]
    if set(req.args) != set(wanted):
        raise HTTPException(422, f"{req.name} takes exactly these arguments: {', '.join(wanted)}")
    work = lab_work()
    shown = run_tool(work, req.name, req.args)
    return {"shown_to_the_model": shown[:6000], "chars": len(shown),
            "state": {"links found by searches": len(work["found"]), "pages read": len(work["kept"]), "notes": work["notes"],
                      "skills loaded": work["skills"], "finished": work["report"]},
            "links": list(work["found"])[:8]}


@router.post("/offload/{source_id}")
def offload(source_id: str, req: Text) -> dict:
    """What offloading does to one stored page: its full size, the part a researcher is shown, and a look back into the rest."""
    from harness.config import CFG
    from harness.evidence import choose_excerpts, source_text
    found = oracle.rows("SELECT title, content_chars FROM survey_sources WHERE paper_id = :p AND source_id = :s",
                        {"p": lab_paper(), "s": source_id})
    if not found:
        raise HTTPException(404, "No such page in the practice library.")
    page = source_text(source_id, limit=60_000)["content"]
    return {"title": found[0]["title"], "stored_chars": found[0]["content_chars"],
            "shown_chars": min(len(page), CFG.page_digest_chars), "kept_out_of_the_conversation": max(0, len(page) - CFG.page_digest_chars),
            "recalled": choose_excerpts(page, [req.text], 2)}


@router.post("/compact")
def compact() -> dict:
    """Compaction on demand, on its own: a conversation that holds two stored pages is replaced by a summary of it."""
    from harness.evidence import source_text, sources_for
    from harness.llm import HOUSE_RULES
    from harness.research import KEEP, RESEARCH_TOOLS
    from harness.llm import summarise_conversation
    pages = [source_text(s["source_id"], limit=6000) for s in sources_for(lab_paper())[:2]]
    if not pages:
        raise HTTPException(409, "The practice library is empty. Send a researcher out first, in the tools chapter.")
    messages = [{"role": "user", "content": f"Research the section '{LAB['section']['title']}'. Purpose: {LAB['section']['purpose']}"}]
    for page in pages:
        messages += [{"role": "assistant", "content": f"I will read [{page['source_id']}] {page['title']}."},
                     {"role": "user", "content": f"[{page['source_id']}] {page['title']}\n\n{page['content']}"}]
    summary = summarise_conversation(HOUSE_RULES, messages, RESEARCH_TOOLS, KEEP, LAB_PAPER, "lab")
    if summary is None:
        raise HTTPException(502, "No summary came back. Try again.")
    text = next(block.content for block in summary.content if block.type == "compaction")
    before = sum(len(m["content"]) for m in messages)
    return {"messages_before": len(messages), "chars_before": before, "summary": text, "chars_after": len(text),
            "call": calls(1)}


@router.post("/research")
def research(req: Brief) -> dict:
    """Send one researcher out for the practice section: a tool loop with offloading and compaction."""
    from harness.reading import notes_for
    from harness.research import research_section
    from harness.tables import paper_ledger
    rounds = oracle.rows("SELECT NVL(MAX(round), 0) AS r FROM survey_sources WHERE paper_id = :p", {"p": lab_paper()})[0]["r"]
    before = len(calls(200))
    done = research_section(LAB_PAPER, LAB["subject"], LAB["section"], req.queries, int(rounds) + 1, req.missing or None)
    return {"done": {k: done[k] for k in ("turns", "searches", "skills", "notes", "compactions", "coverage", "missing")},
            "pages": done["kept"], "calls": calls(200)[before:],
            "notes": [{k: n[k] for k in ("source_id", "title", "year", "kind", "relevance", "contribution")} for n in notes_for(LAB_PAPER)],
            "compactions": [e for e in paper_ledger(LAB_PAPER) if e["kind"] == "compaction"][-done["compactions"] or None:] if done["compactions"] else []}


@router.post("/reflect")
def reflect() -> dict:
    from harness.reading import reflect_on_evidence
    found = reflect_on_evidence(lab_paper(), LAB["subject"], [LAB["section"]])
    return {"verdict": found[0] if found else None, "call": calls(1)}


# ── memory ────────────────────────────────────────────────────────────────────

@router.post("/remember")
def remember(req: Memory) -> dict:
    from harness.memory import recall, remember as store
    stored = store(LAB_READER, req.content, req.kind, replaces=req.replaces or None)
    return {**stored, "memories": recall(LAB_READER, LAB["subject"], limit=12)}


@router.post("/recall")
def recall(req: Text) -> dict:
    from harness.memory import recall as find
    return {"memories": find(LAB_READER, req.text, limit=12)}


@router.post("/forget")
def forget() -> dict:
    from harness.memory import forget_reader
    forget_reader(LAB_READER)
    return {"memories": []}


# ── planner ───────────────────────────────────────────────────────────────────

@router.post("/plan")
def plan(req: Text) -> dict:
    from harness.memory import recall as find
    from harness.writing import scope_paper
    remembered = find(LAB_READER, req.text)
    found = scope_paper(req.text, "researchers and engineers building agent systems", lab_paper(), remembered)
    return {"remembered": remembered, "plan": found, "call": calls(1)}


# ── writer and verifier ───────────────────────────────────────────────────────

@router.post("/quote")
def quote(req: Quote) -> dict:
    from harness.evidence import on_the_page
    return {"on_the_page": on_the_page(req.quote, req.page), "words": len(req.quote.split())}


@router.post("/claims")
def claims(req: Text) -> dict:
    from harness.writing import cited_claims
    return {"claims": cited_claims(req.text)}


@router.get("/excerpts/{source_id}")
def excerpts(source_id: str) -> dict:
    from harness.evidence import choose_excerpts, source_text
    from harness.reading import notes_for
    notes = notes_for(LAB_PAPER, source_ids=[source_id])
    if not notes:
        raise HTTPException(404, "This source has no note yet. The note says what to look for.")
    note = notes[0]
    page = source_text(source_id, limit=60_000)["content"]
    return {"title": note["title"], "pointers": note["claims"],
            "excerpts": choose_excerpts(page, [*note["claims"], note["evidence"], note["contribution"]])}


@router.post("/write")
def write() -> dict:
    """The whole loop for the practice section: write, check each claim, repair once, enforce."""
    from harness.reading import notes_for
    from harness.writing import build_taxonomy, write_section
    if not notes_for(lab_paper()):
        raise HTTPException(409, "Send a researcher out first, in the tools chapter: the writer needs notes.")
    if LAB["framework"] is None:
        LAB["framework"] = build_taxonomy(LAB_PAPER, LAB["subject"])
    before = len(calls(50))
    result = write_section(LAB_PAPER, LAB["subject"], f"A survey of {LAB['subject']}", LAB["section"], LAB["framework"], 1)
    draft = oracle.rows("SELECT draft FROM survey_sections WHERE paper_id = :p AND section_key = 'lab'", {"p": LAB_PAPER})[0]["draft"]
    checked = oracle.rows("SELECT n, claim, source_id, verdict, quote, on_page, outcome FROM survey_claims "
                          "WHERE paper_id = :p ORDER BY n", {"p": LAB_PAPER})
    return {"result": {k: result[k] for k in ("words", "citations", "claims", "supported", "repaired", "removed")},
            "draft": draft, "claims": checked, "calls": calls(50)[before:] or calls(4)}
