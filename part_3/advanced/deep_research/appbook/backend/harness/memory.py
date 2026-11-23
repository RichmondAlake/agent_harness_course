"""What the harness remembers between papers, on Oracle Agent Memory."""
from __future__ import annotations

import hashlib
import re

from oracleagentmemory.apis import RecordStatus
from oracleagentmemory.core import (MemoryExtractionConfig, MemoryRetentionConfig, OracleAgentMemory,
                                    OracleDBMemoryStore, SchemaPolicy, SearchIndexSyncMode, SearchStrategy)
from oracleagentmemory.core.embedders import OracleDBEmbedder

from shared.oracle import ORA, pool

from .config import CFG

_memory: dict[str, object] = {}
KINDS = ["preference", "guideline", "fact"]      # what the reader wants, what earlier papers taught, what was published


def agent_memory() -> OracleAgentMemory:
    """One memory store for every reader, built on first use. Embeddings are made inside the database,
    search is hybrid (meaning and keywords), and a memory expires after a year unless it is renewed."""
    if "client" not in _memory:
        embedder = OracleDBEmbedder(connection=pool("memory", max=4), model=ORA.embed_model, input_name="DATA",
                                    embedding_dimension=384, normalize=True, batch_size=16)
        store = OracleDBMemoryStore(
            embedder=embedder, pool=pool("memory", max=4), schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,
            memory_store_id=CFG.memory_store_id, search_strategy=SearchStrategy.HYBRID,
            search_index_sync=SearchIndexSyncMode.ON_COMMIT,
            memory_retention_config=MemoryRetentionConfig(default_ttl_days=365))
        _memory["store"] = store
        _memory["client"] = OracleAgentMemory(      # the harness decides what is worth remembering, so extraction is off
            store=store, memory_extraction_config=MemoryExtractionConfig(extract_memories=False))
        if store.get("agent_profile", CFG.agent_id) is None:
            _memory["client"].add_agent(CFG.agent_id, "Survey-paper research harness")
    return _memory["client"]


def ensure_reader(reader: str) -> None:
    client = agent_memory()
    if _memory["store"].get("user_profile", reader) is None:
        client.add_user(reader, "A person who asks the harness for survey papers")


def memory_key(reader: str, content: str) -> str:
    """One id for one statement by one reader, so storing it twice stores it once and readers never collide."""
    said = re.sub(r"\s+", " ", content).strip().lower()
    return "mem-" + hashlib.sha256(f"{reader}|{said}".encode()).hexdigest()[:24]


def remember(reader: str, content: str, kind: str = "preference", paper_id: str = "", replaces: str | None = None) -> dict:
    """Store one statement. When it replaces an older one, the two are linked and the older one is retired."""
    ensure_reader(reader)
    key = memory_key(reader, content)
    if _memory["store"].get(kind, key) is not None:
        return {"memory_id": key, "stored": False}
    link = {"memory_id_to_link": replaces, "link_type": "supersedes"} if replaces else {}
    agent_memory().add_memory(content, memory_type=kind, memory_id=key, user_id=reader, agent_id=CFG.agent_id,
                              metadata={"paper_id": paper_id}, autonomous_linking=False, **link)
    if replaces:
        agent_memory().update_memory(replaces, status=RecordStatus.INVALID)     # kept as history, no longer recalled
    return {"memory_id": key, "stored": True}


def recall(reader: str, query: str, limit: int = 8) -> list[dict]:
    """What is remembered that bears on a subject: this reader's memories only, retired ones left out,
    and no more than 600 tokens of them, so memory cannot crowd the prompt."""
    ensure_reader(reader)
    found = agent_memory().search(query, user_id=reader, agent_id=CFG.agent_id, exact_user_match=True,
                                  exact_agent_match=True, exact_thread_match=False, max_results=limit,
                                  record_types=KINDS, include_invalid_results=False, token_budget=600)
    return [{"kind": item.record.record_type, "content": item.record.content, "distance": round(item.distance, 3),
             "memory_id": item.record.id} for item in found]


def forget_reader(reader: str) -> None:
    ensure_reader(reader)
    agent_memory().delete_user(reader, cascade=True)
