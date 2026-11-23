"""The three notebooks: parts, stars, diagrams as images, no secrets, and no Mermaid left as text."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ADVANCED = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "deep_research": ADVANCED / "deep_research" / "notebook" / "advanced_survey_paper_harness.ipynb",
    "metaharness": ADVANCED / "metaharness" / "notebook" / "advanced_metaharness_memorizz.ipynb",
}
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|tvly-[A-Za-z0-9]{20,}|apikey_[0-9a-f]{20,}")


@pytest.mark.parametrize("name", sorted(NOTEBOOKS))
def test_the_notebook_is_built_for_the_course(name: str):
    notebook = json.loads(NOTEBOOKS[name].read_text())
    cells = notebook["cells"]
    markdown = [c for c in cells if c["cell_type"] == "markdown"]
    code = [c for c in cells if c["cell_type"] == "code"]
    parts = [c for c in markdown if "".join(c["source"]).startswith("## Part ")]
    assert len(parts) >= 7, "the notebook is segmented by parts"
    assert any("⭐" in "".join(c["source"]) for c in parts), "some parts are starred for the live path"
    assert not any("```mermaid" in "".join(c["source"]) for c in markdown), "diagrams are embedded as images"
    assert sum(len(c.get("attachments", {})) for c in markdown) >= 3, "the diagrams are attached"
    assert all(len("".join(c["source"]).splitlines()) <= 70 for c in code), "no long code cells"
    assert "## Key takeaways" in "".join("".join(c["source"]) for c in markdown)
    text = json.dumps(notebook)
    assert not SECRET.search(text), "no key in the notebook"
    assert str(Path.home()) not in text, "no machine path in the notebook"


@pytest.mark.parametrize("name", sorted(NOTEBOOKS))
def test_the_executed_notebook_has_no_errors(name: str):
    notebook = json.loads(NOTEBOOKS[name].read_text())
    code = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    executed = [c for c in code if c.get("outputs")]
    if not executed:
        pytest.skip("the notebook has not been executed")
    errors = [c for c in code if any(o.get("output_type") == "error" for o in c.get("outputs", []))]
    assert not errors, f"{len(errors)} cells ended in an error"
