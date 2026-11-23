"""The researcher: one agent for one section, working with tools.

The model decides what to search for, which pages to read, which reading skill to load and
when it has enough. The harness decides what the tools may do, how much of a page enters the
conversation, when the conversation is summarised, and when the researcher must stop.

The researcher is a LangGraph graph of its own: an ``agent`` node that calls the model, a
``tools`` node that runs the tool calls, and a ``compact`` node that summarises.
"""
from __future__ import annotations

import copy
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from shared.oracle import rows

from .config import CFG
from .evidence import (choose_excerpts, clean_title, keep_source, known_works, new_results, read_pages, search_web,
                       source_text, work_keys)
from .llm import HOUSE_RULES, ask_with_tools, summarise_conversation
from .reading import save_note
from .semantics import vocabulary_for, vocabulary_text
from .skills import load_skill, skill_manifest, skills_for
from .tables import ledger

RESEARCH = """You research one section of a survey paper on "{subject}".

Work with the tools. Search for scholarly sources, read the ones that bear on the section, and take one note
for every page you read. Before you take your first note on a kind of source, load the skill that fits it and
follow it. Prefer primary papers to summaries of them. You may read at most {pages} pages, so choose with care.
When the section's purpose is covered, or the pages are used, call finish and say what is still missing."""

NOTE = {"source_id": {"type": "string"},
        "kind": {"type": "string", "enum": ["paper", "preprint", "documentation", "blog", "report", "other"]},
        "year": {"type": "string"}, "venue": {"type": "string"}, "contribution": {"type": "string"},
        "method": {"type": "string"}, "evidence": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "string"}},
        "relevance": {"type": "string", "enum": ["high", "medium", "low"]}}


def tool(name: str, description: str, properties: dict) -> dict:
    """A tool as the model sees it: a name, when to use it, and the exact shape of its arguments."""
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties, "required": list(properties),
                             "additionalProperties": False}}


RESEARCH_TOOLS = [
    tool("search_web", "Search scholarly sites. Call this to find sources for the section. Returns titles, links and snippets.",
         {"query": {"type": "string"}}),
    tool("read_page", "Read one page from your search results. The full text is stored in the library and you get the "
                      "start of it with a source id. Only links that a search returned can be read.",
         {"url": {"type": "string"}}),
    tool("load_skill", "Load the full procedure of one skill from the SKILLS list, by name. Call this before taking "
                       "notes on a kind of source you have not handled yet in this conversation.",
         {"name": {"type": "string"}}),
    tool("take_note", "Store the note for one page you have read. One note per source id. Record only what the page supports.",
         NOTE),
    tool("recall", "Look again at a page you read earlier, by source id. Returns the passages that best match your question. "
                   "Use it when the text of a page is no longer in the conversation.",
         {"source_id": {"type": "string"}, "question": {"type": "string"}}),
    tool("finish", "End the research for this section. Say whether the evidence is enough, and what is still missing.",
         {"coverage": {"type": "string", "enum": ["enough", "thin"]}, "missing": {"type": "array", "items": {"type": "string"}}}),
]

KEEP = ("Summarise this research session so that it can continue from the summary alone. Keep: the section and its "
        "purpose; every source id read, with its title and one line on what it showed; which source ids already have "
        "a note; the searches already made; the skills already loaded and their main rules; what is still missing. "
        "Do not call tools. Respond with the summary only.")


def run_tool(work: dict, name: str, args: dict) -> str:
    """Run one tool call for a researcher and return what the model is shown. Every limit is enforced here."""
    paper_id, section = work["paper_id"], work["section"]
    if name == "search_web":
        found = new_results(paper_id, search_web(args["query"]))
        work["found"].update({r["url"]: {**r, "title": clean_title(r["title"]), "query": args["query"]} for r in found})
        work["searches"].append(args["query"])
        return "\n".join(f"{r['url']} | {clean_title(r['title'])} | {r['snippet'][:220]}" for r in found) or "Nothing new found."
    if name == "read_page":
        if args["url"] not in work["found"]:
            return "Not read: only links returned by your searches can be read. Search first."
        if len(work["kept"]) >= CFG.sources_per_section:
            return "Not read: the page limit for this section is reached. Take your notes, then finish."
        result = work["found"][args["url"]]
        if work_keys(result["url"], result["title"]) & known_works(paper_id):
            return "Not read: the library already holds this work, perhaps from another address."
        page = read_pages([args["url"]]).get(args["url"]) or result["snippet"]
        source_id = keep_source(paper_id, section["key"], result["query"], result, page, work["round"])
        if source_id is None:
            return "Not read: another section already stored this page."
        work["kept"].append({"source_id": source_id, "section_key": section["key"], "url": args["url"],
                             "title": result["title"], "chars": len(page)})
        return (f"[{source_id}] {result['title']}\nStored in full ({len(page)} characters). This is the first "
                f"{min(len(page), CFG.page_digest_chars)}. Use recall to look further into it.\n\n{page[:CFG.page_digest_chars]}")
    if name == "load_skill":
        body = load_skill(args["name"])
        work["skills"] += [args["name"]] if body else []
        return body or "No skill has that name. Use a name from the SKILLS list."
    if name == "take_note":
        stored = save_note(paper_id, args)
        work["notes"] += stored
        return f"Note stored for {args['source_id']}." if stored else "No such source id in this paper. Read the page first."
    if name == "recall":
        page = source_text(args["source_id"], limit=60_000)["content"] if rows(
            "SELECT 1 FROM survey_sources WHERE paper_id = :p AND source_id = :s", {"p": paper_id, "s": args["source_id"]}) else ""
        return "\n\n".join(choose_excerpts(page, [args["question"]], 2)) or "No such source id in this paper."
    work["report"] = {"coverage": args["coverage"], "missing": args["missing"]}
    return "Recorded. The research for this section is closed."


def conversation_tokens(reply) -> int:
    """How large the next request will be: everything sent this turn, plus the reply that will be sent back."""
    use = reply.usage
    return use.input_tokens + (use.cache_read_input_tokens or 0) + (use.cache_creation_input_tokens or 0) + use.output_tokens


class ResearchState(TypedDict):
    """What one researcher carries from step to step. LangGraph saves it after every step."""
    system: str            # house rules, instructions, vocabulary and the skill list for this section
    messages: list         # the conversation, in the shape the model API takes
    work: dict             # links found, pages kept, searches made, skills loaded, notes taken, the verdict
    turns: int
    tokens: int            # how large the next request will be
    compactions: int


def call_model(state: ResearchState) -> dict:
    """The agent node: one model call. The reply joins the conversation."""
    work = state["work"]
    reply = ask_with_tools(state["system"], state["messages"], RESEARCH_TOOLS, work["paper_id"], work["section"]["key"])
    return {"messages": state["messages"] + [{"role": "assistant", "content": reply.to_dict()["content"]}],
            "turns": state["turns"] + 1, "tokens": conversation_tokens(reply)}


def after_agent(state: ResearchState) -> str:
    """A reply that asks for tools goes to the tool node. A reply that asks for none ends the research."""
    return "tools" if any(block["type"] == "tool_use" for block in state["messages"][-1]["content"]) else END


def run_tools(state: ResearchState) -> dict:
    """The tool node: run every tool call in the last reply, and answer each with a tool result."""
    work = copy.deepcopy(state["work"])
    results = [{"type": "tool_result", "tool_use_id": block["id"], "content": run_tool(work, block["name"], block["input"])}
               for block in state["messages"][-1]["content"] if block["type"] == "tool_use"]
    return {"messages": state["messages"] + [{"role": "user", "content": results}], "work": work}


def after_tools(state: ResearchState) -> str:
    """The harness decides what follows the tools: stop, summarise, or ask the model again."""
    if state["work"]["report"] or state["turns"] >= CFG.max_research_turns:
        return END
    return "compact" if state["tokens"] > CFG.compact_at_tokens else "agent"


def compact(state: ResearchState) -> dict:
    """The compaction node: a summary takes the place of the conversation it covers."""
    work = state["work"]
    summary = summarise_conversation(state["system"], state["messages"], RESEARCH_TOOLS, KEEP, work["paper_id"],
                                     work["section"]["key"])
    if summary is None:
        return {"tokens": 0}
    ledger(work["paper_id"], "gather", "compaction", {"section": work["section"]["key"], "turn": state["turns"],
                                                       "tokens_before": state["tokens"]})
    return {"messages": [{"role": "assistant", "content": summary.to_dict()["content"]},
                         {"role": "user", "content": "Continue the research from this summary."}],
            "tokens": 0, "compactions": state["compactions"] + 1}


def researcher_graph():
    """agent → tools → agent, until the model stops asking or the harness says stop."""
    builder = StateGraph(ResearchState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", run_tools)
    builder.add_node("compact", compact)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", after_agent, ["tools", END])
    builder.add_conditional_edges("tools", after_tools, ["agent", "compact", END])
    builder.add_edge("compact", "agent")
    return builder.compile()


RESEARCHER = researcher_graph()


def research_section(paper_id: str, subject: str, section: dict, queries: list[str], round_no: int = 1,
                     missing: list[str] | None = None) -> dict:
    """One researcher, one section, one round: build its starting state, run its graph, report what it did."""
    topic = f"{section['title']}. {section['purpose']}"
    system = "\n\n".join([HOUSE_RULES, RESEARCH.format(subject=subject, pages=CFG.sources_per_section),
                          vocabulary_text(vocabulary_for(topic)), skill_manifest(skills_for(topic))])
    brief = (f"Section: {section['title']}\nPurpose: {section['purpose']}\nSearches to start from: {'; '.join(queries)}"
             + (f"\nAn earlier round left these gaps: {'; '.join(missing)}" if missing else ""))
    work = {"paper_id": paper_id, "section": section, "round": round_no, "found": {}, "kept": [], "searches": [],
            "skills": [], "notes": 0, "report": None}
    start = {"system": system, "messages": [{"role": "user", "content": brief}], "work": work, "turns": 0, "tokens": 0,
             "compactions": 0}
    end = RESEARCHER.invoke(start, {"recursion_limit": 3 * CFG.max_research_turns + 5})
    work = end["work"]
    report = work["report"] or {"coverage": "thin", "missing": ["the researcher ran out of turns"]}
    return {"section": section["key"], "round": round_no, "kept": work["kept"], "notes": work["notes"], "turns": end["turns"],
            "searches": work["searches"], "skills": work["skills"], "compactions": end["compactions"], **report}
