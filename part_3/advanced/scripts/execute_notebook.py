"""Execute a notebook in place with this interpreter's kernel and keep its outputs.

    python part_3/advanced/scripts/execute_notebook.py path/to/notebook.ipynb [--timeout 1800]

Secrets are read from the environment; nothing is written into the notebook
but what the cells print. A cell that prints a key would be a bug in the cell.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|tvly-[A-Za-z0-9]{20,}|apikey_[0-9a-f]{20,}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    path = Path(args.notebook).resolve()
    notebook = nbformat.read(path, as_version=4)
    for noisy in ("MallocStackLogging", "MallocStackLoggingNoCompact"):   # macOS prints a line per child otherwise
        os.environ.pop(noisy, None)
    manager = KernelManager(kernel_cmd=[sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"])
    client = NotebookClient(notebook, km=manager, timeout=args.timeout, allow_errors=False,
                            resources={"metadata": {"path": str(path.parent)}})
    started = time.perf_counter()
    try:
        client.execute()
    finally:
        for cell in notebook.cells:                      # an install log names machine paths; it is noise
            if cell.cell_type == "code" and cell.source.lstrip().startswith("%pip"):
                cell.outputs = []
            for output in cell.get("outputs", []):       # a macOS malloc notice per child process is noise too
                if output.get("output_type") == "stream" and "MallocStackLogging" in str(output.get("text", "")):
                    output["text"] = "".join(line for line in str(output["text"]).splitlines(keepends=True)
                                             if "MallocStackLogging" not in line)
            if cell.cell_type == "code":
                cell.outputs = [o for o in cell.get("outputs", []) if not (o.get("output_type") == "stream" and not o.get("text"))]
        nbformat.write(notebook, path)
    code = [c for c in notebook.cells if c.cell_type == "code"]
    errors = [c for c in code if any(o.get("output_type") == "error" for o in c.get("outputs", []))]
    text = "\n".join(str(o.get("text", "")) + str(o.get("data", "")) for c in code for o in c.get("outputs", []))
    leaked = SECRET.findall(text)
    print(f"{path.name}: {len(code)} code cells, {len(errors)} errors, {time.perf_counter() - started:.0f} s, "
          f"secrets in output: {len(leaked)}")
    return 1 if errors or leaked else 0


if __name__ == "__main__":
    sys.exit(main())
