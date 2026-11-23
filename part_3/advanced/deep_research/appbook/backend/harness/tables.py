"""The evidence library and the paper's own tables in Oracle AI Database.

A survey is only as good as what it read. Every page the harness reads is a
row in ``SURVEY_SOURCES`` with an embedding made inside the database, so a
writer can ask for more evidence by meaning, and every citation in the paper
resolves to a row that holds the page it came from. Every cited claim that was
checked is a row in ``SURVEY_CLAIMS``, and every model call a priced row in
``SURVEY_MODEL_CALLS``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from shared.oracle import ddl, execute, rows

SURVEY_TABLES = ["survey_papers", "survey_sources", "survey_notes", "survey_sections", "survey_claims",
                 "survey_reviews", "survey_model_calls", "survey_ledger"]


def create_library_tables() -> None:
    """The paper, the pages it read, and the notes on them."""
    ddl("""CREATE TABLE survey_papers (
        paper_id VARCHAR2(40) PRIMARY KEY, subject VARCHAR2(500) NOT NULL, brief CLOB, status VARCHAR2(30) NOT NULL,
        title VARCHAR2(500), outline CLOB, taxonomy CLOB, markdown CLOB, html CLOB, usage CLOB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP, updated_at TIMESTAMP WITH TIME ZONE)""")
    ddl("""CREATE TABLE survey_sources (
        source_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, section_key VARCHAR2(60),
        url VARCHAR2(2000) NOT NULL, title VARCHAR2(1000), published VARCHAR2(40), query VARCHAR2(1000),
        score NUMBER, snippet VARCHAR2(4000), content CLOB, content_chars NUMBER, round NUMBER,
        embedding VECTOR(384, FLOAT32), fetched_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
        CONSTRAINT survey_sources_once UNIQUE (paper_id, url))""")
    ddl("""CREATE TABLE survey_notes (
        note_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, source_id VARCHAR2(40) NOT NULL,
        kind VARCHAR2(30), year VARCHAR2(10), venue VARCHAR2(200), contribution VARCHAR2(2000),
        method VARCHAR2(2000), evidence VARCHAR2(2000), claims CLOB, relevance VARCHAR2(10))""")


def create_writing_tables() -> None:
    """The drafts, the claims that were checked, and the referee's passes."""
    ddl("""CREATE TABLE survey_sections (
        paper_id VARCHAR2(40) NOT NULL, section_key VARCHAR2(60) NOT NULL, position NUMBER, title VARCHAR2(300),
        draft CLOB, words NUMBER, citations NUMBER, round NUMBER, written_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT survey_sections_pk PRIMARY KEY (paper_id, section_key))""")
    ddl("ALTER TABLE survey_sections ADD (claims NUMBER, supported NUMBER, repaired NUMBER, removed NUMBER)")
    ddl("""CREATE TABLE survey_claims (
        claim_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, section_key VARCHAR2(60) NOT NULL,
        n NUMBER, claim VARCHAR2(4000), source_id VARCHAR2(40), verdict VARCHAR2(20), quote VARCHAR2(2000),
        on_page NUMBER, outcome VARCHAR2(20))""")
    ddl("""CREATE TABLE survey_reviews (
        review_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, round NUMBER, verdict VARCHAR2(20),
        findings CLOB, at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP)""")


def create_record_tables() -> None:
    """What every model call cost, and the diary of every step and decision."""
    ddl("""CREATE TABLE survey_model_calls (
        call_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, kind VARCHAR2(30) NOT NULL,
        section_key VARCHAR2(60), input_tokens NUMBER, cache_write_tokens NUMBER, cache_read_tokens NUMBER,
        output_tokens NUMBER, cost_usd NUMBER, seconds NUMBER, at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP)""")
    ddl("""CREATE TABLE survey_ledger (
        entry_id VARCHAR2(40) PRIMARY KEY, paper_id VARCHAR2(40) NOT NULL, node VARCHAR2(40) NOT NULL,
        kind VARCHAR2(30) NOT NULL, detail CLOB, at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP)""")


def create_knowledge_tables() -> None:
    """What the agent is given to work with: an agreed vocabulary, and written procedures."""
    ddl("""CREATE TABLE survey_terms (
        term VARCHAR2(100) PRIMARY KEY, definition VARCHAR2(1000) NOT NULL, avoid VARCHAR2(1000),
        embedding VECTOR(384, FLOAT32))""")
    ddl("""CREATE TABLE survey_skills (
        name VARCHAR2(80) PRIMARY KEY, description VARCHAR2(500) NOT NULL, body CLOB,
        embedding VECTOR(384, FLOAT32))""")


def create_survey_tables() -> None:
    create_library_tables()
    create_writing_tables()
    create_record_tables()
    create_knowledge_tables()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger(paper_id: str, node: str, kind: str, detail) -> None:
    execute("INSERT INTO survey_ledger (entry_id, paper_id, node, kind, detail) VALUES (:1, :2, :3, :4, :5)",
            [new_id("L"), paper_id, node, kind, detail if isinstance(detail, str) else json.dumps(detail, default=str)])


def paper_ledger(paper_id: str) -> list[dict]:
    return rows("SELECT node, kind, detail, at FROM survey_ledger WHERE paper_id = :p ORDER BY at, entry_id",
                {"p": paper_id})


def reset_survey_tables() -> None:
    for table in SURVEY_TABLES:
        execute(f"DELETE FROM {table}")
