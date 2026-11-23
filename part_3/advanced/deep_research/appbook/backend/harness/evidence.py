"""Finding, reading and storing evidence. The library is searchable by meaning."""
from __future__ import annotations

import re
from collections import Counter

import oracledb

from shared.oracle import EMBED, execute, rows

from .config import CFG, tavily
from .tables import new_id


def canonical(url: str) -> str:
    """One key per work: an arXiv paper is the same paper whether it is read as abs, html or pdf."""
    found = re.search(r"arxiv\.org/(?:abs|html|pdf)/(\d{4}\.\d{4,5})", url)
    if found:
        return f"arxiv:{found.group(1)}"
    return re.sub(r"#.*$", "", url.rstrip("/")).lower()


def clean_title(title: str) -> str:
    """Titles as a search engine shows them carry the site's name; the reference list should not."""
    title = re.sub(r"^\[(PDF|HTML)\]\s*", "", title.strip())
    title = re.sub(r"\s*[|·–-]\s*(arXiv|Semantic Scholar|Springer Nature Link|OpenReview|ACM Digital Library|IEEE Xplore|Nature|ScienceDirect)\s*$", "", title)
    return title.strip() or "Untitled"


def search_web(query: str, scholarly: bool = True) -> list[dict]:
    """One search. Scholarly searches stay on the venues where papers live."""
    options = {"search_depth": "advanced", "max_results": CFG.results_per_query}
    if scholarly:
        options["include_domains"] = list(CFG.scholarly_domains)
    found = tavily().search(query, **options)
    return [{"url": item.get("url", ""), "title": item.get("title", ""), "snippet": item.get("content", "")[:2000],
             "score": item.get("score"), "published": (item.get("published_date") or "")[:10]}
            for item in found.get("results", []) if item.get("url")]


def read_pages(urls: list[str]) -> dict[str, str]:
    """The full text of each page, as the search service extracts it."""
    if not urls:
        return {}
    found = tavily().extract(urls=urls)
    return {item["url"]: (item.get("raw_content") or "")[:60_000] for item in found.get("results", [])}


def work_keys(url: str, title: str = "") -> set[str]:
    """What one work is known by: its address, and its title when the title is long enough to be one."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"^\[[^\]]*\]\s*", "", clean_title(title).lower()))
    return {canonical(url)} | ({"title:" + " ".join(words)} if len(words) >= 4 else set())


def known_works(paper_id: str) -> set[str]:
    stored = rows("SELECT url, title FROM survey_sources WHERE paper_id = :p", {"p": paper_id})
    return set().union(*(work_keys(row["url"], row["title"]) for row in stored))


def new_results(paper_id: str, results: list[dict]) -> list[dict]:
    """The results whose work the library does not hold yet, one result per work."""
    seen, fresh = known_works(paper_id), []
    for result in results:
        keys = work_keys(result["url"], result["title"])
        if not keys & seen:
            fresh.append(result)
            seen |= keys
    return fresh


def keep_source(paper_id: str, section_key: str, query: str, result: dict, content: str, round_no: int) -> str | None:
    """One page becomes one row, embedded inside the database as it is stored.

    Sections gather in parallel, so two of them can find the same new page at the
    same moment. The unique constraint on (paper, url) decides: the second insert
    is refused and the page is kept once, under the section that stored it first.
    """
    source_id = new_id("S")
    seed = f"{result['title']}\n{result['snippet']}"[:4000]
    try:
        execute(f"""INSERT INTO survey_sources (source_id, paper_id, section_key, url, title, published, query, score,
                    snippet, content, content_chars, round, embedding)
                    VALUES (:id, :p, :s, :u, :t, :d, :q, :sc, :sn, :c, :n, :r, {EMBED})""",
                {"id": source_id, "p": paper_id, "s": section_key, "u": result["url"][:2000], "t": result["title"][:1000],
                 "d": result.get("published", ""), "q": query[:1000], "sc": result.get("score"), "sn": result["snippet"][:4000],
                 "c": content, "n": len(content), "r": round_no, "text": seed})
    except oracledb.IntegrityError:
        return None
    return source_id


def sources_for(paper_id: str, section_key: str | None = None) -> list[dict]:
    where = "paper_id = :p" + (" AND section_key = :s" if section_key else "")
    binds = {"p": paper_id, **({"s": section_key} if section_key else {})}
    return rows(f"SELECT source_id, section_key, url, title, published, content_chars, round FROM survey_sources "
                f"WHERE {where} ORDER BY fetched_at", binds)


def similar_sources(paper_id: str, text: str, limit: int = 5, exclude_section: str | None = None) -> list[dict]:
    """The library, asked by meaning: the sources closest to a piece of text."""
    where = "paper_id = :p" + (" AND section_key <> :s" if exclude_section else "")
    binds = {"p": paper_id, "text": text[:4000], "k": limit, **({"s": exclude_section} if exclude_section else {})}
    return rows(f"""SELECT source_id, section_key, title, url,
                           ROUND(VECTOR_DISTANCE(embedding, {EMBED}, COSINE), 4) AS distance
                      FROM survey_sources WHERE {where}
                     ORDER BY distance FETCH FIRST :k ROWS ONLY""", binds)


STOPWORDS = set("a an and are as at be by for from has have in is it its of on or that the their this to was were "
                "which with we our can more than these those not but also into over such between using used use".split())


def words_of(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2]


def passages(content: str, size: int = 700) -> list[str]:
    """A page cut into passages of a few sentences, so one of them can travel as evidence."""
    out, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+|\n{2,}", re.sub(r"[ \t]+", " ", content)):
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + len(sentence) > size:
            out.append(current)
            current = ""
        current = f"{current} {sentence}".strip()[:size * 2]
    return out + ([current] if current else [])


def choose_excerpts(content: str, pointers: list[str], limit: int | None = None) -> list[str]:
    """The passages of a page that best match what its note says the page shows.

    A note is the model's reading of a page. An excerpt is the page itself. For
    each thing the note points at, the harness picks the passage that shares the
    most uncommon words with it. No model is asked: this is counting.
    """
    limit = limit or CFG.excerpts_per_source
    found = passages(content[:40_000])
    if not found:
        return []
    bags = [set(words_of(p)) for p in found]
    rarity = Counter(word for bag in bags for word in bag)
    chosen: list[int] = []
    for pointer in pointers:
        wanted = set(words_of(pointer))
        scores = [sum(1 / rarity[w] for w in wanted & bag) for bag in bags]
        best = max(range(len(found)), key=lambda i: scores[i])
        if scores[best] > 0 and best not in chosen:
            chosen.append(best)
        if len(chosen) == limit:
            break
    return [found[i] for i in sorted(chosen)] or found[:1]


def on_the_page(quote: str, content: str) -> bool:
    """Whether a quote really is in a page: the same letters and digits in the same order.

    Extracted pages lose hyphens, spaces and line breaks, so everything except letters and
    digits is ignored. Nothing else is forgiven: one changed word or number and the quote is
    not on the page. A quote of fewer than five words proves nothing and is refused.
    """
    squeeze = lambda text: re.sub(r"[^a-z0-9]", "", text.lower())
    return len(re.findall(r"[A-Za-z0-9]+", quote)) >= 5 and squeeze(quote) in squeeze(content)


def source_text(source_id: str, limit: int = 14_000) -> dict:
    found = rows("SELECT source_id, title, url, published, content FROM survey_sources WHERE source_id = :s",
                 {"s": source_id})[0]
    text = re.sub(r"\n{3,}", "\n\n", found["content"] or "")
    return {**found, "content": text[:limit]}
