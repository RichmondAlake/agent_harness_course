"""Names a notebook's code cells use without defining or importing them. A static check, before execution."""
from __future__ import annotations

import ast
import builtins
import json
import sys


def undefined_names(path: str) -> list[str]:
    notebook = json.load(open(path))
    code = "\n".join("".join(c["source"]) for c in notebook["cells"]
                     if c["cell_type"] == "code" and not "".join(c["source"]).lstrip().startswith("%"))
    tree = ast.parse(code)
    defined = set(dir(builtins)) | {"In", "Out", "get_ipython", "display"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Import):
            defined |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            defined |= {(a.asname or a.name) for a in node.names}
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.Global):
            defined |= set(node.names)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted(used - defined)


if __name__ == "__main__":
    bad = 0
    for path in sys.argv[1:]:
        missing = undefined_names(path)
        print(path.split("/")[-1], "possibly undefined:", missing or "none")
        bad += bool(missing)
    sys.exit(bad)
