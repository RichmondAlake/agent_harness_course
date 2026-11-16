"""The context and cost ledger: what each turn put in the prompt, and what each model call cost.

Two records feed it.

* ``ppa_model_calls`` has one row for each model call: which turn, which step,
  how many input tokens were fresh, written to the prompt cache or read from
  it, how many tokens came out, how long the call took and what it cost.
* ``ppa_turns.context_layers`` has the approximate size of every layer the
  harness put in the prompt for that turn.

An input token is billed in one of three ways. A *fresh* token is read at the
full input price. A token *written* to the prompt cache costs a little more
than fresh. A token *read* from the cache costs a twentieth of fresh. The
model reports the three counts; this module multiplies them by the prices in
``config``.

With the scripted responder no model is called. The ledger still writes a row
for each step, with zero tokens and zero cost, and says so in ``note``.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from backend.config import settings
from backend.core import store

SCRIPTED_NOTE = "scripted responder, no model call"
LAYERS = ("system prompt", "tool schemas", "now", "what you remember", "memories", "governed meanings",
          "skills", "request")
LAYER_ABOUT = {
    "system prompt": "Who the assistant is and the rules it works under. Fixed for a conversation.",
    "tool schemas": "The name, purpose and arguments of every tool. Fixed for a conversation.",
    "now": "The clock, the session, the workspace, working rules and working notes.",
    "what you remember": "Standing memory: preferences and guidelines that always apply.",
    "memories": "Memories recalled for this request.",
    "governed meanings": "The written definitions of urgent, free, VIP and the rest.",
    "skills": "One line for each live skill. A full procedure enters only when it is loaded.",
    "request": "What the owner typed, or what a routine asked for.",
}
STABLE_LAYERS = ("system prompt", "tool schemas")


def prices() -> dict[str, float]:
    """US dollars per million tokens, by the way a token is billed."""
    return {"fresh": settings.price_fresh_input, "cache_write": settings.price_cache_write,
            "cache_read": settings.price_cache_read, "output": settings.price_output}


def approximate_tokens(text: str) -> int:
    """A stated approximation: four characters to a token."""
    return len(text) // 4


def split(usage: dict[str, int], *, input_includes_cache: bool = True) -> dict[str, int]:
    """Turn a model's usage report into the four billed counts.

    LangChain's ``input_tokens`` counts every input token, cached or not, so the fresh
    tokens are what is left once the cache reads and cache writes are taken away. The
    raw Anthropic SDK reports the fresh tokens directly; pass ``input_includes_cache=False``
    for a report of that kind.
    """
    read = int(usage.get("cache_read_tokens", 0) or 0)
    write = int(usage.get("cache_write_tokens", 0) or 0)
    given = int(usage.get("input_tokens", 0) or 0)
    fresh = given - read - write if input_includes_cache else given
    return {"fresh": max(fresh, 0), "cache_write": write, "cache_read": read,
            "output": int(usage.get("output_tokens", 0) or 0)}


def cost(counts: dict[str, int]) -> float:
    """What the four counts cost, in US dollars."""
    price = prices()
    return round(sum(counts.get(kind, 0) * price[kind] for kind in price) / 1e6, 6)


def saved_by_cache(cache_read_tokens: int) -> float:
    """What the cache-read tokens would have cost at the fresh price, less what they did cost."""
    price = prices()
    return round(cache_read_tokens * (price["fresh"] - price["cache_read"]) / 1e6, 6)


def record(turn_id: str, step: int, usage: dict[str, int], seconds: float, *, scripted: bool) -> dict[str, Any]:
    """Write one row for one model call. A scripted step is written as a zero-cost row."""
    counts = {"fresh": 0, "cache_write": 0, "cache_read": 0, "output": 0} if scripted else split(usage)
    usd = 0.0 if scripted else cost(counts)
    store.execute(
        "INSERT INTO ppa_model_calls(turn_id,step,fresh_tokens,cache_write_tokens,cache_read_tokens,"
        "output_tokens,seconds,usd,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (turn_id, step, counts["fresh"], counts["cache_write"], counts["cache_read"], counts["output"],
         round(seconds, 3), usd, SCRIPTED_NOTE if scripted else "", store.real_now()))
    return {**counts, "usd": usd}


def calls(turn_id: str) -> list[dict[str, Any]]:
    return store.rows("SELECT * FROM ppa_model_calls WHERE turn_id=? ORDER BY rowid", (turn_id,))


def _total(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fresh = sum(int(row["fresh_tokens"]) for row in rows)
    write = sum(int(row["cache_write_tokens"]) for row in rows)
    read = sum(int(row["cache_read_tokens"]) for row in rows)
    given = fresh + write + read
    return {"model_calls": len(rows), "scripted_steps": sum(1 for row in rows if row["note"] == SCRIPTED_NOTE),
            "fresh_tokens": fresh, "cache_write_tokens": write, "cache_read_tokens": read,
            "input_tokens": given, "output_tokens": sum(int(row["output_tokens"]) for row in rows),
            "seconds": round(sum(float(row["seconds"]) for row in rows), 3),
            "usd": round(sum(float(row["usd"]) for row in rows), 6),
            "cache_read_share": round(read / given, 4) if given else None,
            "saved_by_cache_usd": saved_by_cache(read)}


def turn_total(turn_id: str) -> dict[str, Any]:
    return _total(calls(turn_id))


def summary(limit: int = 40) -> dict[str, Any]:
    """Every figure the chapter draws, newest turn last."""
    turns = store.rows("SELECT turn_id,thread_id,kind,request,planned_by,context_layers,outcome,started_at,"
                       "ended_at FROM ppa_turns ORDER BY rowid DESC LIMIT ?", (limit,))
    turns.reverse()
    every = store.rows("SELECT * FROM ppa_model_calls ORDER BY rowid")
    by_turn: dict[str, list[dict[str, Any]]] = {}
    for row in every:
        by_turn.setdefault(row["turn_id"], []).append(row)
    shaped, running = [], 0.0
    for turn in turns:
        rows = by_turn.get(turn["turn_id"], [])
        total = _total(rows)
        running = round(running + total["usd"], 6)
        layers = store.loads(turn["context_layers"], {})
        shaped.append({**turn, "context_layers": layers,
                       "context_tokens": sum(int(value) for value in layers.values()),
                       "scripted": bool(rows) and total["scripted_steps"] == len(rows),
                       **total, "cumulative_usd": running})
    overall = _total(every)
    seconds = [turn["seconds"] for turn in shaped if turn["model_calls"]]
    costs = [turn["usd"] for turn in shaped if turn["model_calls"]]
    return {"turns": shaped, "totals": {
        **overall, "turns": len(shaped),
        "median_turn_seconds": round(median(seconds), 3) if seconds else None,
        "median_turn_usd": round(median(costs), 6) if costs else None,
        "all_scripted": bool(every) and overall["scripted_steps"] == len(every)},
        "prices": prices(), "layers": [{"name": name, "about": LAYER_ABOUT[name],
                                        "stable": name in STABLE_LAYERS} for name in LAYERS],
        "method": "Layer sizes are approximate: the number of characters divided by four. Token counts "
                  "of model calls are the model's own report.",
        "scripted_note": SCRIPTED_NOTE}
