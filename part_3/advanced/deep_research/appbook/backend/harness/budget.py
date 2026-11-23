"""The budget: what a paper has spent, what a kind of call costs, and which optional work still fits."""
from __future__ import annotations

from shared.oracle import rows

from .config import CFG
from .tables import ledger

FIRST_GUESS = {"scope": 0.08, "research": 0.022, "compact": 0.07, "reflect": 0.10, "taxonomy": 0.30, "section": 0.10, "claims": 0.05,
               "repair": 0.08, "review": 0.20, "abstract": 0.06}       # USD per call, used until the paper has its own figures
SECTION_CALLS = {"section": 1, "claims": 2, "repair": 1}                # one section: write, check, repair, check again
RESEARCH_CALLS = {"research": 9, "compact": 1}                          # one researcher, one section, one round


def usage(paper_id: str | None = None) -> dict:
    """The bill so far, for one paper or for all of them: calls, tokens by price, and dollars."""
    where = "WHERE paper_id = :p" if paper_id else ""
    return rows(f"""SELECT COUNT(*) AS calls, NVL(SUM(input_tokens), 0) AS fresh_tokens,
                           NVL(SUM(cache_write_tokens), 0) AS cache_write_tokens,
                           NVL(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                           NVL(SUM(output_tokens), 0) AS output_tokens, ROUND(NVL(SUM(cost_usd), 0), 2) AS cost_usd
                      FROM survey_model_calls {where}""", {"p": paper_id} if paper_id else {})[0]


def typical(paper_id: str, kind: str) -> float:
    """What a call of this kind has cost in this paper so far, or a first guess when there is none yet."""
    found = rows("SELECT AVG(cost_usd) AS usd FROM survey_model_calls WHERE paper_id = :p AND kind = :k",
                 {"p": paper_id, "k": kind})[0]["usd"]
    return float(found) if found else FIRST_GUESS[kind]


def estimate(paper_id: str, calls: dict[str, float]) -> float:
    return sum(typical(paper_id, kind) * count for kind, count in calls.items())


def grant(paper_id: str, node: str, what: str, asked: list, each: dict[str, float], reserve: dict[str, float]) -> list:
    """The part of ``asked`` that fits. ``each`` is the calls one item needs; ``reserve`` is what the paper must
    still pay to be finished, which optional work may not touch. The decision goes into the ledger."""
    used, kept_back, one = usage(paper_id)["cost_usd"], estimate(paper_id, reserve), estimate(paper_id, each)
    room = CFG.budget_usd - used - kept_back
    fits = max(0, min(len(asked), int(room // one))) if one else len(asked)
    ledger(paper_id, node, "budget", {"for": what, "asked": len(asked), "granted": fits, "each_usd": round(one, 3),
                                      "spent_usd": round(used, 2), "reserved_usd": round(kept_back, 2),
                                      "budget_usd": CFG.budget_usd})
    return asked[:fits]
