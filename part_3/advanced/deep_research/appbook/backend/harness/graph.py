"""The research graph: plan, ask, then search, read and reflect until the evidence is enough; organise, write and
check each section, review, revise within the budget, assemble, ask."""
from __future__ import annotations

import json
import os
from operator import add
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from langgraph_oracledb.checkpoint.oracle import OracleSaver

from shared.oracle import execute, pool, rows

from .budget import RESEARCH_CALLS, SECTION_CALLS, grant, usage
from .config import CFG
from .evidence import sources_for
from .memory import recall, remember
from .reading import notes_for, reflect_on_evidence
from .research import research_section
from .semantics import seed_vocabulary
from .skills import seed_skills
from .tables import create_survey_tables, ledger, new_id
from .writing import assemble_paper, build_taxonomy, check_drafts, drafts, review_paper, scope_paper, write_section

OUTPUT_DIR = Path(os.getenv("SURVEY_OUTPUT_DIR", "output"))     # where published papers are written
EVIDENCE_KINDS = {"background", "framework", "thematic", "evaluation", "outlook"}


class PaperState(TypedDict, total=False):
    paper_id: str
    reader: str                  # who asked: memory is kept and recalled for this person
    subject: str
    audience: str
    remembered: list[dict]       # what memory returned when the paper was planned
    title: str
    scope: dict
    outline: list[dict]
    note: str
    rescopes: int
    sources: Annotated[list, add]
    written: Annotated[list, add]
    research_round: int          # how many times the harness has searched
    reflection: list[dict]       # what the model said about the evidence, section by section
    follow_up: list[dict]        # the searches the harness decided to make next
    taxonomy: dict
    review: dict
    problems: list[dict]
    revise: list[dict]           # the sections the harness decided to write again
    round: int                   # how many times the paper has been written
    paper: dict
    decision: dict
    status: str
    log: Annotated[list, add]


class Crashed(RuntimeError):
    """Stands in for a process that died: the step's work is in the database, its checkpoint is not."""


def note_step(state: PaperState, node: str, kind: str, detail: Any) -> dict:
    ledger(state["paper_id"], node, kind, detail)
    return {"log": [{"node": node, "kind": kind, "detail": detail}]}


def maybe_crash(node: str) -> None:
    """For the resume proof: stop here, after the work but before the checkpoint. LangGraph sees what it
    would see if the process had died: the step never finished, so nothing of it was checkpointed."""
    if CFG.crash_after == node:
        raise Crashed(f"the process died inside {node}")


def set_status(paper_id: str, status: str, **fields) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    execute(f"UPDATE survey_papers SET status = :status, updated_at = SYSTIMESTAMP{', ' + sets if sets else ''} "
            f"WHERE paper_id = :paper_id", {"status": status, "paper_id": paper_id, **fields})


# ── nodes ────────────────────────────────────────────────────────────────────

def scope(state: PaperState) -> dict:
    request = state["subject"] + (f"\n\nThe reader of the previous outline asked: {state['note']}" if state.get("note") else "")
    remembered = recall(state["reader"], state["subject"])
    found = scope_paper(request, state["audience"], state["paper_id"], remembered)
    outline = [{**s, "position": n + 1} for n, s in enumerate(found["sections"])]
    changed = execute("UPDATE survey_papers SET outline = :o, title = :t, status = 'OUTLINED', updated_at = SYSTIMESTAMP "
                      "WHERE paper_id = :id", {"o": json.dumps(outline), "t": found["title"][:500], "id": state["paper_id"]})
    if not changed:
        execute("INSERT INTO survey_papers (paper_id, subject, brief, status, title, outline) "
                "VALUES (:id, :sub, :b, 'OUTLINED', :t, :o)",
                {"id": state["paper_id"], "sub": state["subject"][:500], "b": json.dumps({"audience": state["audience"]}),
                 "t": found["title"][:500], "o": json.dumps(outline)})
    return {"scope": found, "title": found["title"], "outline": outline, "remembered": remembered,
            "status": "awaiting_outline",
            **note_step(state, "scope", "outline", [(s["key"], s["title"]) for s in outline])}


def outline_review(state: PaperState) -> dict:
    """Nothing is read, and little is paid for, before a person accepts the plan."""
    decision = interrupt({"paper_id": state["paper_id"], "title": state["title"], "scope": state["scope"],
                          "outline": state["outline"], "remembered": state.get("remembered", []),
                          "options": ["approve", "revise", "reject"]})
    if decision.get("note"):          # what the reader says about a plan is worth keeping for the next one
        remember(state["reader"], decision["note"], "preference", state["paper_id"])
    return {"decision": decision, "note": decision.get("note", ""),
            **note_step(state, "outline_review", "decision", decision)}


def after_outline_review(state: PaperState):
    verdict = state["decision"].get("decision")
    if verdict == "revise" and state.get("rescopes", 0) < 2:
        return "rescope"
    if verdict != "approve":
        return "close"
    return [Send("gather", {"paper_id": state["paper_id"], "subject": state["subject"], "section": s,
                            "queries": s["queries"], "round": 1})
            for s in state["outline"] if s["kind"] in EVIDENCE_KINDS]


def rescope(state: PaperState) -> dict:
    return {"rescopes": state.get("rescopes", 0) + 1, **note_step(state, "rescope", "note", state.get("note", ""))}


def gather(task: dict) -> dict:
    """One researcher for one section: the researcher's graph, run inside this node. Runs beside the others."""
    done = research_section(task["paper_id"], task["subject"], task["section"], task["queries"], task["round"],
                            task.get("missing"))
    detail = {k: done[k] for k in ("section", "round", "turns", "searches", "skills", "compactions", "notes", "coverage")}
    detail["kept"] = len(done["kept"])
    ledger(task["paper_id"], "gather", "sources", detail)
    return {"sources": done["kept"], "log": [{"node": "gather", "kind": "sources", "detail": detail}]}


def tally(state: PaperState) -> dict:
    """Where the researchers join. It counts what the library and the notes hold now, and calls no model."""
    held = {"sources": len(sources_for(state["paper_id"])), "notes": len(notes_for(state["paper_id"]))}
    set_status(state["paper_id"], "READ")
    return {"status": "read", **note_step(state, "tally", "library", held)}


def after_tally(state: PaperState) -> str:
    """Before the paper is written, research leads to reflection. In a revision it leads straight back to writing."""
    return "reflect" if state.get("round", 0) == 0 else "organise"


def reflect(state: PaperState) -> dict:
    """The model says which sections are thin and what to search for. The harness decides whether to search.

    It searches again only when a section is thin, a round is left, the last round
    found something new, and the budget has room after what the paper still needs.
    """
    paper_id, done = state["paper_id"], state.get("research_round", 1)
    sections = [s for s in state["outline"] if s["kind"] in EVIDENCE_KINDS]
    found = reflect_on_evidence(paper_id, state["subject"], sections)
    held = {s["key"]: len(sources_for(paper_id, s["key"])) for s in sections}
    thin = sorted((f for f in found if f["coverage"] == "thin" and f["queries"]), key=lambda f: held[f["key"]])
    fresh = sum(1 for s in sources_for(paper_id) if s["round"] == done)
    follow_up, reason = [], "every section has enough evidence"
    if thin and done >= CFG.max_research_rounds:
        reason = "the round limit is reached"
    elif thin and fresh == 0:
        reason = "the last round found nothing new"
    elif thin:
        to_finish = {"taxonomy": 1, "review": 1, "abstract": 1, "reflect": 1,
                     **{kind: calls * len(state["outline"]) for kind, calls in SECTION_CALLS.items()}}
        follow_up = grant(paper_id, "reflect", "follow-up searches", thin, RESEARCH_CALLS, to_finish)
        reason = "researching again" if follow_up else "the budget has no room for more research"
    detail = {"round": done, "thin": [f["key"] for f in thin], "decision": reason,
              "searching": {f["key"]: f["queries"] for f in follow_up}}
    return {"reflection": found,
            "follow_up": [{"key": f["key"], "queries": f["queries"], "missing": f["missing"]} for f in follow_up],
            "research_round": done + (1 if follow_up else 0), **note_step(state, "reflect", "decision", detail)}


def after_reflect(state: PaperState):
    if not state.get("follow_up"):
        return "organise"
    keys = {s["key"]: s for s in state["outline"]}
    return [Send("gather", {"paper_id": state["paper_id"], "subject": state["subject"], "section": keys[f["key"]],
                            "queries": f["queries"], "missing": f["missing"], "round": state["research_round"]})
            for f in state["follow_up"]]


def organise(state: PaperState) -> dict:
    """The framework is built once, from the notes, and saved on the paper's row. If it is already there,
    because this is a revision or because the run was cut off after it was saved, it is used as it is."""
    saved = rows("SELECT taxonomy FROM survey_papers WHERE paper_id = :p", {"p": state["paper_id"]})[0]["taxonomy"]
    if saved:
        taxonomy = json.loads(saved)
        return {"taxonomy": taxonomy, "round": state.get("round", 0) + 1,
                **note_step(state, "organise", "kept", taxonomy["framework_name"])}
    taxonomy = build_taxonomy(state["paper_id"], state["subject"])
    maybe_crash("organise")
    return {"taxonomy": taxonomy, "round": state.get("round", 0) + 1,
            **note_step(state, "organise", "taxonomy", {"framework": taxonomy["framework_name"],
                                                         "categories": [c["name"] for c in taxonomy["categories"]],
                                                         "compared": len(taxonomy["comparison"]["rows"])})}


def fan_out_write(state: PaperState):
    feedback = {s["key"]: s for s in state.get("review", {}).get("sections", [])}
    again = {r["key"] for r in state.get("revise", [])}
    to_write = state["outline"] if state.get("round", 1) == 1 else [s for s in state["outline"] if s["key"] in again]
    return [Send("write", {"paper_id": state["paper_id"], "subject": state["subject"], "title": state["title"],
                           "section": s, "taxonomy": state["taxonomy"], "round": state.get("round", 1),
                           "feedback": feedback.get(s["key"])}) for s in to_write]


def write(task: dict) -> dict:
    """One section: written from its evidence, checked claim by claim, repaired once. Runs beside the other sections."""
    result = write_section(task["paper_id"], task["subject"], task["title"], task["section"], task["taxonomy"],
                           task["round"], task.get("feedback"))
    ledger(task["paper_id"], "write", "section", result)
    return {"written": [result], "log": [{"node": "write", "kind": "section", "detail": result}]}


def review(state: PaperState) -> dict:
    """The harness's rules, the referee's opinion, and the decision about what to write again.

    A revision is optional work, so it has to fit the budget: the sections with the
    most to fix come first, and only as many as the money allows.
    """
    paper_id = state["paper_id"]
    problems = check_drafts(paper_id, state["outline"])
    found = review_paper(paper_id, state["subject"], state["outline"])
    verdict = "accept" if found["verdict"] == "accept" and not problems else "revise"
    revise = []
    if verdict == "revise" and state.get("round", 1) < CFG.max_rounds:
        broken = {p["key"] for p in problems}
        wanted = sorted((s for s in found["sections"]
                         if s["needs_more_evidence"] or s["unsupported_claims"] or s["key"] in broken),
                        key=lambda s: -(10 * (s["key"] in broken) + len(s["unsupported_claims"]) + len(s["missing"])))
        granted = grant(paper_id, "review", "sections to revise", wanted, {**SECTION_CALLS, **RESEARCH_CALLS},
                        {"review": 1, "abstract": 1})
        revise = [{"key": s["key"], "queries": s["queries"][:2] if s["needs_more_evidence"] else []} for s in granted]
    return {"review": found, "problems": problems, "revise": revise, "status": f"reviewed_{verdict}",
            **note_step(state, "review", "verdict", {"verdict": verdict, "problems": problems,
                                                      "revising": [r["key"] for r in revise],
                                                      "summary": found["summary"][:400]})}


def after_review(state: PaperState):
    if not state.get("revise"):
        return "assemble"
    keys = {s["key"]: s for s in state["outline"]}
    searches = [Send("gather", {"paper_id": state["paper_id"], "subject": state["subject"], "section": keys[r["key"]],
                                "queries": r["queries"], "round": state.get("research_round", 1) + 1})
                for r in state["revise"] if r["queries"] and r["key"] in keys]
    return searches or "organise"


def assemble(state: PaperState) -> dict:
    paper = assemble_paper(state["paper_id"], state["subject"], state["title"], state["outline"], state["review"])
    set_status(state["paper_id"], "ASSEMBLED", markdown=paper["markdown"], usage=json.dumps(usage(state["paper_id"])))
    return {"paper": paper, "status": "awaiting_publication",
            **note_step(state, "assemble", "paper", {**paper["counts"], "release": paper["release"]["verdict"]})}


def publication_review(state: PaperState) -> dict:
    """The person sees the release check and the referee's verdict. A blocked paper needs more than a yes."""
    release = state["paper"]["release"]
    decision = interrupt({"paper_id": state["paper_id"], "title": state["title"], "counts": state["paper"]["counts"],
                          "abstract": state["paper"]["abstract"], "release": release,
                          "options": ["approve", "reject"] if release["verdict"] == "READY" else ["override", "reject"]})
    return {"decision": decision, **note_step(state, "publication_review", "decision", decision)}


def after_publication_review(state: PaperState) -> str:
    said, ready = state["decision"].get("decision"), state["paper"]["release"]["verdict"] == "READY"
    return "publish" if said == "override" or (said == "approve" and ready) else "close"


def publish(state: PaperState) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file = OUTPUT_DIR / f"{state['paper_id']}.md"
    file.write_text(state["paper"]["markdown"])
    set_status(state["paper_id"], "PUBLISHED")
    lessons = [remember(state["reader"], f"A survey on {state['subject']} should cover: {point.split(': ', 1)[-1]}",
                        "guideline", state["paper_id"]) for point in state["paper"]["release"]["open_points"][:6]]
    remember(state["reader"], f"Published the survey \"{state['title']}\" on {state['subject']} "
                              f"({state['paper']['counts']['sources_cited']} sources cited).", "fact", state["paper_id"])
    files = {"file": str(file), "overridden": state["decision"].get("decision") == "override",
             "lessons_remembered": sum(lesson["stored"] for lesson in lessons)}
    return {"status": "published", "paper": {**state["paper"], **files},
            **note_step(state, "publish", "files", files)}


def close(state: PaperState) -> dict:
    held = state.get("paper") and state["decision"].get("decision") == "approve"     # a yes on a blocked paper
    set_status(state["paper_id"], "HELD" if held else "DECLINED")
    return {"status": "held" if held else "declined",
            **note_step(state, "close", "closed", "held: the release check is BLOCKED" if held else "declined")}


# ── the graph ────────────────────────────────────────────────────────────────

def build_graph(saver=None):
    graph = StateGraph(PaperState)
    for name, node in [("scope", scope), ("outline_review", outline_review), ("rescope", rescope), ("gather", gather),
                       ("tally", tally), ("reflect", reflect), ("organise", organise), ("write", write),
                       ("review", review), ("assemble", assemble), ("publication_review", publication_review),
                       ("publish", publish), ("close", close)]:
        graph.add_node(name, node)
    graph.add_edge(START, "scope")
    graph.add_edge("scope", "outline_review")
    graph.add_conditional_edges("outline_review", after_outline_review, ["rescope", "close", "gather"])
    graph.add_edge("rescope", "scope")
    graph.add_edge("gather", "tally")
    graph.add_conditional_edges("tally", after_tally, ["reflect", "organise"])
    graph.add_conditional_edges("reflect", after_reflect, ["gather", "organise"])
    graph.add_conditional_edges("organise", fan_out_write, ["write"])
    graph.add_edge("write", "review")
    graph.add_conditional_edges("review", after_review, ["assemble", "gather", "organise"])
    graph.add_edge("assemble", "publication_review")
    graph.add_conditional_edges("publication_review", after_publication_review, ["publish", "close"])
    graph.add_edge("publish", END)
    graph.add_edge("close", END)
    return graph.compile(checkpointer=saver or InMemorySaver())


_runtime: dict[str, Any] = {}


def durable_graph():
    if "graph" not in _runtime:
        create_survey_tables()
        if not rows("SELECT 1 FROM survey_terms FETCH FIRST 1 ROWS ONLY"):      # a first run on this database
            seed_vocabulary()
            seed_skills()
        saver = OracleSaver(pool("checkpoints", max=8), json_size_threshold_mb=0.0)
        saver.setup()
        _runtime["saver"] = saver
        _runtime["graph"] = build_graph(saver)
    return _runtime["graph"]


def config_for(paper_id: str) -> dict:
    """One thread per paper. Parallel branches are capped so a small database is not flooded."""
    return {"configurable": {"thread_id": paper_id}, "max_concurrency": 3}


def checkpoints_of(paper_id: str) -> dict:
    """The run's own checkpoints, one per step, and those its researchers wrote under the same thread."""
    saved = rows("""SELECT COUNT(*) AS n, NVL(SUM(CASE WHEN TRIM(checkpoint_ns) IS NULL THEN 1 ELSE 0 END), 0) AS own
                    FROM checkpoints WHERE thread_id = :p""", {"p": paper_id})[0]
    return {"checkpoints": saved["own"], "researcher_checkpoints": saved["n"] - saved["own"]}


def outcome(paper_id: str) -> dict:
    snapshot = durable_graph().get_state(config_for(paper_id))
    values = snapshot.values
    waiting = any(t.interrupts for t in snapshot.tasks)
    stopped = [t.name for t in snapshot.tasks if t.error] or (list(snapshot.next) if not waiting else [])
    status = ("awaiting_person" if waiting else "interrupted" if stopped else values.get("status"))
    interrupt_payload = next((t.interrupts[0].value for t in snapshot.tasks if t.interrupts), None)
    return {"paper_id": paper_id, "status": status, "waiting_for_person": waiting, "asked": interrupt_payload,
            "resume_from": stopped, "next": list(snapshot.next), "title": values.get("title"),
            "outline": values.get("outline", []), "taxonomy": values.get("taxonomy"),
            "remembered": values.get("remembered", []),
            "sources": len(sources_for(paper_id)), "research_round": values.get("research_round", 1),
            "reflection": values.get("reflection", []),
            "sections": [{k: d[k] for k in ("section_key", "title", "words", "citations", "round", "claims", "supported",
                                            "repaired", "removed")} for d in drafts(paper_id)],
            "review": values.get("review"), "problems": values.get("problems", []), "round": values.get("round", 0),
            "revise": values.get("revise", []), "paper": values.get("paper"), "log": values.get("log", []),
            "usage": usage(paper_id), "budget_usd": CFG.budget_usd, **checkpoints_of(paper_id)}


def start_paper(subject: str, audience: str = "researchers and engineers building agent systems",
                paper_id: str | None = None, reader: str = "reader") -> dict:
    paper_id = paper_id or new_id("PAPER")
    durable_graph().invoke({"paper_id": paper_id, "reader": reader, "subject": subject, "audience": audience, "rescopes": 0,
                            "round": 0, "research_round": 1, "sources": [], "written": [], "log": []}, config_for(paper_id))
    return outcome(paper_id)


def resume_paper(paper_id: str, decision: str, note: str = "") -> dict:
    durable_graph().invoke(Command(resume={"decision": decision, "note": note}), config_for(paper_id))
    return outcome(paper_id)


def continue_paper(paper_id: str) -> dict:
    durable_graph().invoke(None, config_for(paper_id))
    return outcome(paper_id)
