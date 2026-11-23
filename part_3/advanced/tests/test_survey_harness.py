"""The survey harness's rules, without a model, a search service or a database."""
from __future__ import annotations

from pathlib import Path

ADVANCED = Path(__file__).resolve().parents[1]


def load(module: str):
    from conftest import load_harness
    return load_harness("deep_research", module)


def test_one_work_has_one_key_whatever_the_link():
    evidence = load("harness.evidence")
    assert evidence.canonical("https://arxiv.org/abs/2407.01489") == evidence.canonical("https://arxiv.org/html/2407.01489v2")
    assert evidence.canonical("https://openreview.net/forum?id=a") != evidence.canonical("https://openreview.net/forum?id=b")


def test_titles_lose_the_site_name():
    evidence = load("harness.evidence")
    assert evidence.clean_title("[PDF] A Survey | Semantic Scholar") == "A Survey"
    assert evidence.clean_title("   ") == "Untitled"


def test_the_harness_rules_name_thin_sections(monkeypatch):
    writing = load("harness.writing")
    monkeypatch.setattr(writing, "drafts", lambda paper_id: [
        {"section_key": "intro", "words": 900, "citations": 1},
        {"section_key": "loop", "words": 120, "citations": 1}])
    outline = [{"key": "intro", "kind": "introduction"}, {"key": "loop", "kind": "thematic"}, {"key": "gone", "kind": "thematic"}]
    problems = writing.check_drafts("P", outline)
    assert {p["key"] for p in problems} == {"loop", "gone"}
    assert any("words" in p["problem"] for p in problems) and any("citations" in p["problem"] for p in problems)


def test_a_revision_searches_only_where_the_harness_decided_to():
    graph = load("harness.graph")
    state = {"paper_id": "P", "subject": "s", "research_round": 2, "outline": [{"key": "loop"}, {"key": "tools"}],
             "revise": [{"key": "loop", "queries": ["q1"]}, {"key": "tools", "queries": []}]}
    sends = graph.after_review(state)
    assert [s.arg["section"]["key"] for s in sends] == ["loop"] and sends[0].arg["round"] == 3
    assert graph.after_review({**state, "revise": [{"key": "tools", "queries": []}]}) == "organise"
    assert graph.after_review({**state, "revise": []}) == "assemble"


def test_reading_leads_to_reflection_only_before_the_paper_is_written():
    graph = load("harness.graph")
    assert graph.after_tally({"round": 0}) == "reflect" and graph.after_tally({"round": 1}) == "organise"
    assert graph.after_reflect({"follow_up": []}) == "organise"


def test_a_blocked_paper_needs_more_than_a_yes():
    graph = load("harness.graph")
    blocked = {"paper": {"release": {"verdict": "BLOCKED"}}}
    assert graph.after_publication_review({**blocked, "decision": {"decision": "approve"}}) == "close"
    assert graph.after_publication_review({**blocked, "decision": {"decision": "override"}}) == "publish"
    assert graph.after_publication_review({"paper": {"release": {"verdict": "READY"}}, "decision": {"decision": "approve"}}) == "publish"


def test_a_quote_counts_only_when_it_is_on_the_page():
    evidence = load("harness.evidence")
    page = "In our study the harness raised task success from 41% to 58% on SWE-bench Verified.\nCompaction cut token use by a third."
    assert evidence.on_the_page("the harness raised task success from 41% to 58% on SWE-bench", page)
    assert evidence.on_the_page("The  harness raised task-success from 41 % to 58 %", page)
    assert not evidence.on_the_page("the harness raised accuracy from 10% to 99% on every task", page)
    assert not evidence.on_the_page("the harness raised task success from 41% to 99%", page), "one changed number fails"
    assert evidence.on_the_page("Compaction cut to- ken use by a third", page), "a line-break hyphen is forgiven"
    assert not evidence.on_the_page("task success", page)


def test_excerpts_are_the_passages_a_note_points_at():
    evidence = load("harness.evidence")
    page = ("Agents fail on long tasks for many reasons. " * 20 + "Compaction cut token use by a third on WebArena. "
            + "Unrelated remarks about the weather follow here. " * 20)
    chosen = evidence.choose_excerpts(page, ["compaction reduced token use on WebArena"], limit=1)
    assert len(chosen) == 1 and "Compaction cut token use" in chosen[0]


def test_cited_claims_are_found_and_failed_ones_are_taken_out():
    writing = load("harness.writing")
    draft = "### Loops\n\nA loop helps [S-aa]. It also costs more [S-bb][S-cc]. Nothing is cited here.\n\n| Work | Note |\n| X | fast [S-aa] |"
    claims = writing.cited_claims(draft)
    assert [c["source_ids"] for c in claims] == [["S-aa"], ["S-bb", "S-cc"], ["S-aa"]]
    results = [{"claim": claims[0]["text"], "source_id": "S-aa", "passed": False},
               {"claim": claims[1]["text"], "source_id": "S-bb", "passed": False},
               {"claim": claims[1]["text"], "source_id": "S-cc", "passed": True}]
    kept, removed = writing.enforce(draft, results)
    assert removed == 2 and "A loop helps" not in kept and "It also costs more [S-cc]." in kept and "Nothing is cited here." in kept


def test_optional_work_is_granted_only_while_the_budget_has_room(monkeypatch):
    budget = load("harness.budget")
    monkeypatch.setattr(budget, "usage", lambda paper_id=None: {"cost_usd": 3.0})
    monkeypatch.setattr(budget, "typical", lambda paper_id, kind: 0.5)
    monkeypatch.setattr(budget, "ledger", lambda *a: None)
    room_for_two = budget.CFG.budget_usd - 3.0 - 1.0 >= 1.0
    granted = budget.grant("P", "review", "sections", ["a", "b", "c", "d", "e", "f"], {"section": 1}, {"review": 2})
    assert len(granted) == int((budget.CFG.budget_usd - 4.0) // 0.5) and room_for_two


def test_the_same_statement_is_remembered_under_one_key():
    memory = load("harness.memory")
    assert memory.memory_key("r", "Do not  cite blog posts.") == memory.memory_key("r", "do not cite blog posts.")
    assert memory.memory_key("r", "a") != memory.memory_key("r", "b")
    assert memory.memory_key("one reader", "a") != memory.memory_key("another reader", "a") and set(memory.KINDS) == {"preference", "guideline", "fact"}


def test_what_memory_holds_goes_into_the_plan(monkeypatch):
    writing = load("harness.writing")
    seen = {}
    monkeypatch.setattr(writing, "ask_typed", lambda instructions, request, *a, **k: seen.update(request=request) or {})
    writing.scope_paper("s", "readers", "P", [{"kind": "preference", "content": "Name the benchmarks."}])
    assert "(preference) Name the benchmarks." in seen["request"]
    writing.scope_paper("s", "readers", "P")
    assert "Remembered" not in seen["request"]


def test_a_tool_is_closed_and_strict_so_the_model_cannot_invent_arguments():
    research = load("harness.research")
    names = [t["name"] for t in research.RESEARCH_TOOLS]
    assert names == ["search_web", "read_page", "load_skill", "take_note", "recall", "finish"]
    for tool in research.RESEARCH_TOOLS:
        schema = tool["input_schema"]
        assert tool["strict"] and schema["additionalProperties"] is False and schema["required"] == list(schema["properties"])


def test_a_researcher_can_only_read_what_a_search_returned_and_only_so_many_pages(monkeypatch):
    research = load("harness.research")
    monkeypatch.setattr(research, "read_pages", lambda urls: {urls[0]: "page text " * 50})
    monkeypatch.setattr(research, "keep_source", lambda *a: "S-0001")
    monkeypatch.setattr(research, "known_works", lambda paper_id: set())
    work = {"paper_id": "P", "section": {"key": "k"}, "round": 1, "found": {}, "kept": [], "searches": [], "skills": [],
            "notes": 0, "report": None}
    assert research.run_tool(work, "read_page", {"url": "https://example.org/x"}).startswith("Not read: only links")
    work["found"]["https://example.org/x"] = {"url": "https://example.org/x", "title": "X", "snippet": "", "query": "q"}
    assert research.run_tool(work, "read_page", {"url": "https://example.org/x"}).startswith("[S-0001] X")
    work["kept"] = [{}] * research.CFG.sources_per_section
    assert "page limit" in research.run_tool(work, "read_page", {"url": "https://example.org/x"})
    assert research.run_tool(work, "finish", {"coverage": "enough", "missing": []}).startswith("Recorded")
    assert work["report"] == {"coverage": "enough", "missing": []}


def test_one_work_is_kept_once_whether_it_comes_from_two_addresses_or_two_sites(monkeypatch):
    evidence = load("harness.evidence")
    stored = [{"url": "https://arxiv.org/html/2605.27922v1", "title": "Harness-Bench: Measuring Harness Effects across Models"}]
    monkeypatch.setattr(evidence, "rows", lambda sql, params=None: stored)
    found = [{"url": "https://arxiv.org/abs/2605.27922", "title": "[2605.27922] Harness-Bench"},
             {"url": "https://www.semanticscholar.org/paper/x", "title": "Harness-Bench: Measuring Harness Effects across Models | Semantic Scholar"},
             {"url": "https://arxiv.org/abs/2507.13334", "title": "[2507.13334] A Survey of Context Engineering for Large Language Models"},
             {"url": "https://arxiv.org/html/2507.13334v1", "title": "A Survey of Context Engineering for Large Language Models"},
             {"url": "https://example.org/a", "title": "Home"}, {"url": "https://example.org/b", "title": "Home"}]
    assert [r["url"] for r in evidence.new_results("P", found)] == [
        "https://arxiv.org/abs/2507.13334", "https://example.org/a", "https://example.org/b"]


class Reply:
    """A model reply as the researcher's nodes use it: content blocks, and the size of the request."""
    def __init__(self, *calls, tokens=100):
        self.calls, self.tokens = calls, tokens

    def to_dict(self):
        return {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": args}
                            for i, (name, args) in enumerate(self.calls)] or [{"type": "text", "text": "done"}]}


def scripted_researcher(monkeypatch, replies, tools_run):
    research = load("harness.research")
    replies = iter(replies)
    monkeypatch.setattr(research, "ask_with_tools", lambda *a, **k: next(replies))
    monkeypatch.setattr(research, "conversation_tokens", lambda reply: reply.tokens)
    monkeypatch.setattr(research, "run_tool", lambda work, name, args: (
        tools_run.append(name), work.update(report=args) if name == "finish" else None, "ok")[-1])
    monkeypatch.setattr(research, "vocabulary_for", lambda text: [])
    monkeypatch.setattr(research, "skills_for", lambda text: [])
    monkeypatch.setattr(research, "ledger", lambda *a, **k: None)
    return research


def test_the_researcher_is_a_graph_of_agent_tools_and_compact():
    research = load("harness.research")
    drawn = research.RESEARCHER.get_graph()
    assert set(drawn.nodes) == {"__start__", "agent", "tools", "compact", "__end__"}
    assert {(e.source, e.target) for e in drawn.edges} == {
        ("__start__", "agent"), ("agent", "tools"), ("agent", "__end__"), ("tools", "agent"), ("tools", "compact"),
        ("tools", "__end__"), ("compact", "agent")}


def test_the_researcher_loops_until_finish_and_summarises_when_the_conversation_is_large(monkeypatch):
    ran = []
    research = scripted_researcher(monkeypatch, [
        Reply(("search_web", {"query": "q"})), Reply(("read_page", {"url": "u"}), tokens=10 ** 6),
        Reply(("finish", {"coverage": "enough", "missing": []}))], ran)

    class Summary:
        def to_dict(self):
            return {"content": [{"type": "compaction", "content": "what was done"}]}
    seen = []
    monkeypatch.setattr(research, "summarise_conversation", lambda system, messages, *a, **k: seen.append(len(messages)) or Summary())
    done = research.research_section("P", "s", {"key": "k", "title": "T", "purpose": "p"}, ["q"])
    assert ran == ["search_web", "read_page", "finish"] and done["turns"] == 3
    assert done["compactions"] == 1 and seen == [5] and done["coverage"] == "enough"


def test_the_researcher_stops_at_the_turn_limit_and_when_the_model_asks_for_no_tool(monkeypatch):
    ran = []
    research = scripted_researcher(monkeypatch, [Reply(("search_web", {"query": "q"}))] * 99, ran)
    done = research.research_section("P", "s", {"key": "k", "title": "T", "purpose": "p"}, ["q"])
    assert done["turns"] == research.CFG.max_research_turns == len(ran) and done["coverage"] == "thin"
    research = scripted_researcher(monkeypatch, [Reply()], ran)
    assert research.research_section("P", "s", {"key": "k", "title": "T", "purpose": "p"}, ["q"])["turns"] == 1


def test_a_researcher_cut_off_inside_a_run_continues_from_its_last_step(monkeypatch):
    """Run inside another graph's node, the researcher's steps are checkpointed with the run's."""
    from typing import TypedDict

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    ran, asked = [], []
    research = scripted_researcher(monkeypatch, [], ran)
    script = [Reply(("search_web", {"query": "q"})), Reply(("read_page", {"url": "u"})), RuntimeError("cut"),
              Reply(("finish", {"coverage": "enough", "missing": []}))]

    def model(*a, **k):
        asked.append(1)
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step
    monkeypatch.setattr(research, "ask_with_tools", model)

    class Run(TypedDict):
        done: dict
    outer = StateGraph(Run)
    outer.add_node("gather", lambda state: {"done": research.research_section("P", "s", {"key": "k", "title": "T", "purpose": "p"}, ["q"])})
    outer.add_edge(START, "gather")
    outer.add_edge("gather", END)
    run, thread = outer.compile(checkpointer=InMemorySaver()), {"configurable": {"thread_id": "t"}}
    try:
        run.invoke({"done": {}}, thread)
    except RuntimeError:
        pass
    assert len(asked) == 3 and ran == ["search_web", "read_page"]
    done = run.invoke(None, thread)["done"]
    assert len(asked) == 4 and ran == ["search_web", "read_page", "finish"] and done["turns"] == 3


def test_the_vocabulary_becomes_prompt_text_and_names_what_not_to_write():
    semantics = load("harness.semantics")
    text = semantics.vocabulary_text([{"term": "agent harness", "definition": "The program around a model.", "avoid": ["agent wrapper"]}])
    assert text.startswith("VOCABULARY.") and "- agent harness: The program around a model. Do not write: agent wrapper." in text
    assert len({term for term, _, _ in semantics.VOCABULARY}) == len(semantics.VOCABULARY) >= 10


def test_a_skill_manifest_shows_what_a_skill_is_for_and_not_how_to_do_it():
    skills = load("harness.skills")
    manifest = skills.skill_manifest([{"name": s["name"], "description": s["description"]} for s in skills.SKILLS])
    for skill in skills.SKILLS:
        assert skill["name"] in manifest and skill["description"] in manifest and skill["body"][:60] not in manifest


def test_the_graph_has_the_shape_the_notebook_describes():
    graph = load("harness.graph")
    drawn = graph.build_graph().get_graph()
    names = {n for n in drawn.nodes if not n.startswith("__")}
    assert names == {"scope", "outline_review", "rescope", "gather", "tally", "reflect", "organise", "write", "review", "assemble",
                     "publication_review", "publish", "close"}


def test_every_component_has_a_lab_route():
    import sys
    backend = ADVANCED / "deep_research" / "appbook" / "backend"
    load("harness.config")                      # puts this track's backend first on the path
    sys.modules.pop("labs", None)
    import labs
    paths = {route.path for route in labs.router.routes}
    for wanted in ("/api/lab/embed", "/api/lab/ledger", "/api/lab/ask", "/api/lab/cache", "/api/lab/budget",
                   "/api/lab/search", "/api/lab/fetch", "/api/lab/similar", "/api/lab/vocabulary", "/api/lab/skills",
                   "/api/lab/skills/{name}", "/api/lab/tools", "/api/lab/tool", "/api/lab/offload/{source_id}",
                   "/api/lab/compact", "/api/lab/research", "/api/lab/reflect", "/api/lab/remember", "/api/lab/recall", "/api/lab/plan", "/api/lab/quote",
                   "/api/lab/claims", "/api/lab/write"):
        assert wanted in paths, wanted
    assert (backend / "labs.py").exists()
