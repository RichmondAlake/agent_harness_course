"""Every chapter opens with the same teaching frame, and Part 3 stands on its own."""
from __future__ import annotations

import re
from pathlib import Path

from conftest import APPBOOK, Api

FRONTEND = APPBOOK / "frontend"
BANNED = re.compile(r"\b(webinar|workshop|lesson|course|class)(es|s)?\b", re.I)


def _registered() -> dict[str, dict]:
    """The chapters the page registers: id, number and title, read from the scripts themselves."""
    found = {}
    for script in sorted(FRONTEND.glob("*.js")):
        for block in re.findall(r"PPA\.register\(\{\s*id: \"(\w+)\",(?: n: (\d+),)? title: \"([^\"]+)\",\s*"
                                r"blurb: \"((?:[^\"\\]|\\.)*)\"", script.read_text(encoding="utf-8")):
            found[block[0]] = {"n": int(block[1]) if block[1] else None, "title": block[2], "blurb": block[3]}
    return found


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def test_there_are_eighteen_pages_numbered_without_a_gap():
    chapters = _registered()
    assert len(chapters) == 17 and chapters["assistant"]["n"] is None
    assert sorted(item["n"] for item in chapters.values() if item["n"]) == list(range(1, 17))
    assert (chapters["context_cost"]["n"], chapters["learning"]["n"], chapters["scorecard"]["n"]) == (14, 15, 16)
    assert chapters["context_cost"]["title"] == "Context and cost"
    assert chapters["learning"]["title"] == "Learning from its own traces"
    assert chapters["scorecard"]["title"] == "Scorecard and release gate"


def test_every_chapter_has_every_teaching_field():
    from backend.core import teaching

    assert set(teaching.CHAPTERS) == set(_registered()), "one frame for each registered chapter, no more"
    for identity, frame in teaching.CHAPTERS.items():
        assert set(teaching.FIELDS) <= set(frame), identity
        assert len(frame["what"]) > 60 and frame["what"].rstrip().endswith("."), identity
        assert len(frame["why"]) > 60 and frame["why"].rstrip().endswith("."), identity
        assert 1 <= len(frame["terms"]) <= 3, identity
        for term in frame["terms"]:
            assert term["term"] and term["definition"].rstrip().endswith("."), (identity, term["term"])
        assert 2 <= len(frame["try"]) <= 4, identity
        for step in frame["try"]:
            assert len(step["do"]) > 10 and len(step["watch"]) > 10, identity
        assert 3 <= len(frame["takeaways"]) <= 4, identity
        assert frame["notebook"] and set(frame["notebook"]) <= set(teaching.PARTS), identity
        assert frame["diagram"]["caption"].endswith("."), identity
    assert teaching.CHAPTERS["context_cost"]["notebook"] == [9, 11]
    assert teaching.CHAPTERS["learning"]["notebook"] == [13]
    assert teaching.CHAPTERS["scorecard"]["notebook"] == [11, 14]
    assert len(teaching.PARTS) == 14


def test_every_diagram_can_be_drawn_top_down():
    from backend.core import teaching

    for identity, frame in teaching.CHAPTERS.items():
        diagram = frame["diagram"]
        nodes = {node["id"]: node for node in diagram["nodes"]}
        assert len(nodes) == len(diagram["nodes"]) >= 3, identity
        cells = {(node["row"], node["col"]) for node in nodes.values()}
        assert len(cells) == len(nodes), f"{identity}: two nodes share a cell"
        assert min(node["row"] for node in nodes.values()) == 0 and max(node["col"] for node in nodes.values()) <= 2
        for node in nodes.values():
            assert node["kind"] in teaching.NODE_KINDS and len(node["label"]) <= 26 and len(node["note"]) <= 32, \
                (identity, node["id"])
        assert diagram["edges"], identity
        for edge in diagram["edges"]:
            source, target = nodes[edge["from"]], nodes[edge["to"]]
            assert edge["label"] and len(edge["label"]) <= 22, (identity, edge)
            assert source["row"] != target["row"], f"{identity}: {edge['from']} and {edge['to']} share a row"
            if source["col"] == target["col"]:
                low, high = sorted((source["row"], target["row"]))
                between = {(row, source["col"]) for row in range(low + 1, high)}
                assert not between & cells, f"{identity}: {edge['from']} to {edge['to']} crosses a node"
        assert sum(edge_target["row"] > nodes[edge["from"]]["row"] for edge in diagram["edges"]
                   for edge_target in [nodes[edge["to"]]]) >= len(diagram["edges"]) - 2, f"{identity}: mostly top-down"


def test_the_frame_and_the_primer_are_served_before_the_harness_is_ready(api: Api):
    served = api.get("/api/teaching")
    assert set(served["chapters"]) == set(_registered()) and served["notebook"].endswith("ppa_custom_harness.ipynb")
    cost = served["chapters"]["context_cost"]
    assert cost["notebook"] == [
        {"part": 9, "title": "Claude: adaptive thinking, a cached prompt and a price on every call"},
        {"part": 11, "title": "One working day, live, and what it cost"}]
    assert api.get("/api/teaching/learning")["notebook"][0]["part"] == 13
    api.get("/api/teaching/no-such-chapter", expect=404)
    primer = served["primer"]
    assert "personal productivity assistant" in primer["ppa"]["text"] and "one mailbox" in primer["ppa"]["text"]
    assert len(primer["ppa"]["does"]) == 6 and "only with your approval" in primer["ppa"]["does"][-1]
    assert "runtime around the model" in primer["harness"]["text"]
    assert [item["question"] for item in primer["harness"]["decides"]] == [
        "What context is admitted", "Which tools can run", "When a person must approve", "What is remembered",
        "What evidence is kept"]


def test_new_text_avoids_the_words_the_author_does_not_use():
    from backend.core import learning, ledger, scorecard, teaching

    texts = _strings(teaching.CHAPTERS) + _strings(teaching.PRIMER) + list(teaching.PARTS.values())
    texts += [item["blurb"] for item in _registered().values()]
    texts += _strings(list(scorecard.CHECKS)) + _strings(learning.DESTINATIONS) + _strings(list(learning.CHECKS))
    texts += _strings(ledger.LAYER_ABOUT)
    texts.append((FRONTEND / "chapters-learning.js").read_text(encoding="utf-8").replace("class=", "").replace(
        "className", "").replace("classList", ""))
    texts.append((FRONTEND / "teaching.js").read_text(encoding="utf-8").replace("class=", ""))
    for text in texts:
        found = [hit.group(0) for hit in BANNED.finditer(text) if hit.group(0).lower() != "class"
                 or "class " in text and "${" not in text]
        assert not found, f"{found} in: {text[:120]}"


def test_the_pages_and_scripts_of_the_new_chapters_are_served(api: Api):
    page = api.client.get("/")
    assert page.status_code == 200
    health = api.get("/api/health")
    assert health["status"] == "ok" and health["ready"] is True and health["responder"] == "scripted responder"
    for script in ("teaching.js", "chapters-learning.js"):
        assert f"/{script}?v=" in page.text
        assert api.client.get(f"/{script}").status_code == 200
    learning = api.client.get("/chapters-learning.js").text
    for route in ("/api/context_cost/status", "/api/learning/status", "/api/scorecard/status"):
        assert route in learning
    styles = api.client.get("/styles.css").text
    assert not re.search(r"border-(left|top):\s*[2-9]px\s+solid\s+var\(--(?!line)", styles), "no accent stripes"
    assert "inset 3px" not in styles


def test_part_3_points_at_nothing_in_part_2():
    from backend import config
    from backend.core import oracle_store

    assert config.SHARED_DIR == APPBOOK.parents[1] / "_shared" and config.SHARED_DIR.parent.name == "part_3"
    assert config.settings.mcp_port != 8941 and (APPBOOK / ".env.example").exists()
    assert oracle_store.schema_name("owner@example.com").startswith("PPA3_")
    assert "8050" in (APPBOOK / "run.sh").read_text(encoding="utf-8")
    checked = [*APPBOOK.glob("backend/**/*.py"), *FRONTEND.glob("*"), APPBOOK / "run.sh",
               *APPBOOK.parents[1].glob("_shared/**/*.py")]
    for path in checked:
        if path.is_file() and path.suffix in {".py", ".js", ".html", ".css", ".sh"}:
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"part_2|\b8020\b|\b8941\b|\b8030\b", text), path
    example = (APPBOOK / ".env.example").read_text(encoding="utf-8")
    for name in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "TAVILY_API_KEY", "PPA_SUBSTRATE", "PPA_RESPONDER", "PORT"):
        assert re.search(rf"^{name}=$", example, re.M), f"{name} is listed with no value"
