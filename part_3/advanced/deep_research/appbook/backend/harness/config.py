"""Settings and clients for the survey-paper harness."""
from __future__ import annotations

import os
from dataclasses import dataclass

from anthropic import Anthropic
from tavily import TavilyClient


@dataclass(frozen=True)
class SurveyConfig:
    model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("SURVEY_EFFORT", "medium")
    budget_usd: float = float(os.getenv("SURVEY_BUDGET_USD", "6.00"))   # what one paper may spend on the model
    sections: int = 3                    # thematic sections between the framework and the evaluation
    queries_per_section: int = 2         # web searches for each section in the first round
    results_per_query: int = 8
    sources_per_section: int = 4         # pages a researcher may read for a section, each round
    max_research_rounds: int = 3         # the planned search, then up to two follow-ups chosen from what was read
    max_rounds: int = 2                  # a review may send the harness back to revise once
    min_citations_per_section: int = 3
    min_words_per_section: int = 350
    excerpts_per_source: int = 3         # passages of a page that travel with its note into an evidence pack
    wide_pack: int = 16                  # sources from the rest of the library for a section about the whole field
    max_removed_share: float = 0.20      # more cited claims than this removed, and the paper is not ready
    max_research_turns: int = 14         # model calls one researcher may make for a section, each round
    page_digest_chars: int = 9000        # how much of a page enters the conversation; the rest stays in the library
    compact_at_tokens: int = 14_000      # when a researcher's conversation is larger than this, it is summarised
    max_term_slips: int = 10             # avoided words tolerated in a whole paper
    scholarly_domains: tuple = ("arxiv.org", "openreview.net", "aclanthology.org", "dl.acm.org",
                                "ieeexplore.ieee.org", "proceedings.neurips.cc", "proceedings.mlr.press",
                                "semanticscholar.org", "nature.com", "sciencedirect.com", "springer.com")
    agent_id: str = "survey-harness"     # who the memories belong to, beside the reader
    memory_store_id: str = "SURVEYMEM"
    crash_after: str = os.getenv("SURVEY_CRASH_AFTER", "")   # a node name: the run is cut off there, for the resume proof


CFG = SurveyConfig()
_clients: dict[str, object] = {}


def claude() -> Anthropic:
    if "claude" not in _clients:
        _clients["claude"] = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=3)
    return _clients["claude"]


def tavily() -> TavilyClient:
    if "tavily" not in _clients:
        _clients["tavily"] = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _clients["tavily"]
