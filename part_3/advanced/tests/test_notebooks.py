"""The notebook: parts, diagrams kept as an image with its source, no secrets, and code in step with the appbook."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ADVANCED = Path(__file__).resolve().parents[1]
NOTEBOOKS = {
    "deep_research": ADVANCED / "deep_research" / "notebook" / "advanced_survey_paper_harness.ipynb",
}
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|tvly-[A-Za-z0-9]{20,}|apikey_[0-9a-f]{20,}")


@pytest.mark.parametrize("name", sorted(NOTEBOOKS))
def test_the_notebook_is_built_in_parts(name: str):
    notebook = json.loads(NOTEBOOKS[name].read_text())
    cells = notebook["cells"]
    markdown = [c for c in cells if c["cell_type"] == "markdown"]
    code = [c for c in cells if c["cell_type"] == "code"]
    parts = [c for c in markdown if "".join(c["source"]).startswith("## Part ")]
    assert len(parts) >= 7, "the notebook is segmented by parts"
    images = [image for cell in markdown for image in re.findall(r'<img src="(img/[\w-]+\.png)"', "".join(cell["source"]))]
    assert len(images) >= 3, "the notebook has diagrams"
    assert all((NOTEBOOKS[name].parent / image).exists() for image in images), "every diagram's image file is beside the notebook"
    assert not any(cell.get("attachments") for cell in markdown), "images are files, so splitting a cell cannot lose one"
    assert all(len("".join(c["source"]).splitlines()) <= 70 for c in code), "no long code cells"
    if name == "deep_research":
        assert all(len("".join(c["source"]).splitlines()) <= 45 for c in code), "code cells are short"
        for before, cell in zip(cells, cells[1:]):
            assert cell["cell_type"] != "code" or before["cell_type"] == "markdown", "every code cell is explained first"
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


SOURCES = {     # where the appbook, or a shared module, holds the same functions a notebook defines in its cells
    "deep_research": [ADVANCED / "deep_research" / "appbook" / "backend" / "harness"],
}


def definitions(source: str) -> dict[str, str]:
    """Each top-level function or class of some code, by name, in a form that ignores comments and spacing."""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:                     # a cell with a notebook magic such as %pip
        return {}
    return {node.name: ast.dump(node) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


@pytest.mark.parametrize("name", sorted(NOTEBOOKS))
def test_the_notebook_and_the_appbook_define_the_same_functions(name: str):
    """Nothing generates the notebook, so its code and the package's are two copies. This names what has drifted."""
    in_modules: dict[str, set[str]] = {}
    for folder in SOURCES[name]:
        for module in folder.glob("*.py"):
            for function, shape in definitions(module.read_text()).items():
                in_modules.setdefault(function, set()).add(shape)
    notebook = json.loads(NOTEBOOKS[name].read_text())
    drifted = [function for cell in notebook["cells"] if cell["cell_type"] == "code"
               for function, shape in definitions("".join(cell["source"])).items()
               if function in in_modules and shape not in in_modules[function]]
    assert not drifted, f"these differ between the notebook and the package, change both: {sorted(set(drifted))}"
