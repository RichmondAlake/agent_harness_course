"""Write one survey paper end to end from the command line, approving both gates.

    python part_3/advanced/scripts/survey_run.py "agent harness engineering" [paper_id]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ADVANCED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADVANCED / "deep_research" / "appbook" / "backend"))

from harness import graph  # noqa: E402
from shared import oracle  # noqa: E402


def show(label: str, out: dict, started: float) -> None:
    print(f"[{time.perf_counter() - started:6.0f}s] {label}: status={out['status']} next={out['next']} "
          f"sources={out['sources']} sections={len(out['sections'])} round={out['round']} "
          f"calls={out['usage']['calls']} checkpoints={out['checkpoints']}", flush=True)


if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else "agent harness engineering"
    paper_id = sys.argv[2] if len(sys.argv) > 2 else None
    started = time.perf_counter()
    graph.durable_graph()
    out = graph.start_paper(subject, paper_id=paper_id)
    show("scoped", out, started)
    print("outline:", [(s["position"], s["kind"], s["title"]) for s in out["outline"]], flush=True)
    out = graph.resume_paper(out["paper_id"], "approve")
    show("assembled", out, started)
    if out["status"] == "awaiting_person":
        print("review:", json.dumps(out["review"], indent=0)[:1200], flush=True)
        print("problems:", out["problems"], flush=True)
        print("release:", json.dumps(out["paper"]["release"]["checks"]), flush=True)
        out = graph.resume_paper(out["paper_id"], out["asked"]["options"][0])      # approve, or override when blocked
        show("published", out, started)
        print(json.dumps(out["paper"].get("counts")))
        print("file:", out["paper"].get("file"))
    print("usage", out["usage"])
    oracle.close()
