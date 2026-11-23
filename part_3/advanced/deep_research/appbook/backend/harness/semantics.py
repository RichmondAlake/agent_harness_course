"""The semantic layer: the words this harness uses, what each means, and which words it avoids."""
from __future__ import annotations

import json
import re

from shared.oracle import EMBED, execute, rows

VOCABULARY = [   # (the term to use, what it means here, words to avoid for the same thing)
    ("agent harness", "The program around a model that assembles its context, runs its tools, keeps state and enforces limits.",
     ["agent wrapper", "agent runtime", "agent scaffold"]),
    ("agent loop", "The cycle of model call, tool execution and tool result that repeats until the task ends.",
     ["reasoning loop", "think-act cycle"]),
    ("tool call", "A structured request by the model to run one named tool with arguments.",
     ["function invocation", "action invocation"]),
    ("context window", "The text a model can attend to in one call: instructions, history, tool results.",
     ["prompt buffer", "attention window"]),
    ("context compaction", "Replacing older turns of a conversation with a summary so the context window stays small.",
     ["context compression", "history squashing"]),
    ("context offloading", "Moving content out of the context window into storage the agent can read back on demand.",
     ["context externalisation", "context externalization"]),
    ("agent memory", "What an agent keeps across runs, stored outside the model and recalled when it bears on the task.",
     ["long-term context", "persistent prompt"]),
    ("checkpoint", "A saved copy of a run's state after a step, from which the run can continue.",
     ["state snapshot", "save point"]),
    ("trace", "The recorded sequence of model calls and tool calls in one run, with inputs, outputs and timings.",
     ["trajectory log", "execution transcript"]),
    ("evaluation harness", "The code that runs a benchmark against an agent and scores it. Not the agent harness.",
     ["test rig", "benchmark wrapper"]),
    ("human approval", "A point where the run stops until a person accepts or rejects what is proposed.",
     ["HITL gate", "manual checkpoint"]),
    ("sandbox", "An isolated environment in which an agent's tool calls run, so mistakes cannot reach real systems.",
     ["execution jail", "safe box"]),
]


def seed_vocabulary() -> int:
    """Store the vocabulary. Each term is embedded with its definition, so it can be found by meaning."""
    execute("DELETE FROM survey_terms")
    for term, definition, avoid in VOCABULARY:
        execute(f"INSERT INTO survey_terms (term, definition, avoid, embedding) VALUES (:t, :d, :a, {EMBED})",
                {"t": term, "d": definition, "a": json.dumps(avoid), "text": f"{term}: {definition}"})
    return len(VOCABULARY)


def vocabulary_for(text: str, limit: int = 8) -> list[dict]:
    """The terms that bear on a piece of text, nearest in meaning first."""
    found = rows(f"""SELECT term, definition, avoid, ROUND(VECTOR_DISTANCE(embedding, {EMBED}, COSINE), 3) AS distance
                       FROM survey_terms ORDER BY distance FETCH FIRST :k ROWS ONLY""", {"text": text[:4000], "k": limit})
    return [{**row, "avoid": json.loads(row["avoid"])} for row in found]


def vocabulary_text(terms: list[dict]) -> str:
    """The vocabulary as the block of text that goes into a prompt."""
    lines = [f"- {t['term']}: {t['definition']} Do not write: {', '.join(t['avoid'])}." for t in sorted(terms, key=lambda t: t["term"])]
    return ("VOCABULARY. Use these terms with these meanings. When a source uses another word for the same thing, "
            "write our term.\n" + "\n".join(lines))


def term_slips(text: str) -> dict[str, int]:
    """How often each avoided word appears in a text. The harness can count this; it does not have to ask."""
    found = {}
    for row in rows("SELECT term, avoid FROM survey_terms"):
        for word in json.loads(row["avoid"]):
            count = len(re.findall(rf"\b{re.escape(word)}s?\b", text, flags=re.I))
            if count:
                found[word] = count
    return found
