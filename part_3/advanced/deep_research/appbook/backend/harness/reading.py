"""Typed notes on what was read, and looking back at them to decide what to search next."""
from __future__ import annotations

import json

from shared.oracle import execute, rows

from .llm import ask_typed
from .tables import new_id

def save_note(paper_id: str, note: dict) -> bool:
    """One typed note for one source, stored as it is made. A second note for the same source replaces the first."""
    if not rows("SELECT 1 FROM survey_sources WHERE paper_id = :p AND source_id = :s", {"p": paper_id, "s": note["source_id"]}):
        return False
    execute("DELETE FROM survey_notes WHERE source_id = :s", {"s": note["source_id"]})
    execute("INSERT INTO survey_notes (note_id, paper_id, source_id, kind, year, venue, contribution, method, "
            "evidence, claims, relevance) VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11)",
            [new_id("N"), paper_id, note["source_id"], note["kind"], note["year"][:10], note["venue"][:200],
             note["contribution"][:2000], note["method"][:2000], note["evidence"][:2000],
             json.dumps(note["claims"][:5]), note["relevance"]])
    return True


def notes_for(paper_id: str, section_key: str | None = None, source_ids: list[str] | None = None) -> list[dict]:
    """Notes joined to their sources, for a section or for named sources."""
    if source_ids:
        marks = ", ".join(f":i{n}" for n in range(len(source_ids)))
        binds = {f"i{n}": s for n, s in enumerate(source_ids)}
        where = f"n.source_id IN ({marks})"
    else:
        where = "s.paper_id = :p" + (" AND s.section_key = :k" if section_key else "")
        binds = {"p": paper_id, **({"k": section_key} if section_key else {})}
    found = rows(f"""SELECT n.source_id, s.section_key, s.title, s.url, n.kind, n.year, n.venue, n.contribution,
                            n.method, n.evidence, n.claims, n.relevance
                       FROM survey_notes n JOIN survey_sources s ON s.source_id = n.source_id
                      WHERE {where} ORDER BY n.relevance, s.fetched_at""", binds)
    for row in found:
        row["claims"] = json.loads(row["claims"] or "[]")
    return found


REFLECT = """You steer the research for a survey on "{subject}". For each section you are given its purpose, the
searches already made for it, and one line on every source read for it so far. Decide whether that evidence is
`enough` to write the section, or `thin`. A section is thin when an important part of its purpose has no source,
or when it rests on one or two works. For a thin section, say what is missing and give up to two new web search
queries that would find it. Never repeat a search that was already made."""

REFLECT_SCHEMA = {"type": "object", "properties": {"sections": {"type": "array", "items": {"type": "object", "properties": {
    "key": {"type": "string"}, "coverage": {"type": "string", "enum": ["enough", "thin"]},
    "missing": {"type": "array", "items": {"type": "string"}},
    "queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["key", "coverage", "missing", "queries"]}}}, "required": ["sections"]}


def reflect_on_evidence(paper_id: str, subject: str, sections: list[dict]) -> list[dict]:
    """One call over every section: is what was read enough, and if not, what should be searched next?"""
    notes = notes_for(paper_id)
    searched: dict[str, list[str]] = {}
    for row in rows("SELECT DISTINCT section_key, query FROM survey_sources WHERE paper_id = :p", {"p": paper_id}):
        searched.setdefault(row["section_key"], []).append(row["query"])
    blocks = []
    for section in sections:
        read = [n for n in notes if n["section_key"] == section["key"]]
        lines = "\n".join(f"  - ({n['relevance']}, {n['year'] or 'n.d.'}) {n['title'][:90]}: {n['contribution'][:220]}"
                          for n in read) or "  - nothing read yet"
        blocks.append(f"SECTION {section['key']}: {section['title']}\nPurpose: {section['purpose']}\n"
                      f"Searches made: {'; '.join(searched.get(section['key'], [])) or 'none'}\nRead so far:\n{lines}")
    answer = ask_typed(REFLECT.format(subject=subject), "\n\n".join(blocks), "reflect", REFLECT_SCHEMA,
                       max_tokens=4000, paper_id=paper_id)
    keys = {s["key"] for s in sections}
    return [{**s, "queries": s["queries"][:2]} for s in answer["sections"] if s["key"] in keys]
