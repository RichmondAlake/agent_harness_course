"""Continue a survey paper from its last checkpoint, approving the publication gate when it is reached."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ADVANCED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADVANCED / "deep_research" / "appbook" / "backend"))

from harness import graph  # noqa: E402
from shared import oracle  # noqa: E402

if __name__ == "__main__":
    paper_id = sys.argv[1]
    started = time.perf_counter()
    graph.durable_graph()
    before = graph.outcome(paper_id)
    print("found:", before["status"], "resume from", before["resume_from"], "sources", before["sources"], flush=True)
    out = graph.continue_paper(paper_id) if not before["waiting_for_person"] else graph.resume_paper(paper_id, "approve")
    print(f"[{time.perf_counter()-started:.0f}s] now: {out['status']} next={out['next']} sources={out['sources']} "
          f"sections={len(out['sections'])} round={out['round']} calls={out['usage']['calls']}", flush=True)
    if out["status"] == "awaiting_person" and out["asked"] and "counts" in out["asked"]:
        print("review:", json.dumps(out["review"])[:1500], flush=True)
        print("problems:", out["problems"], flush=True)
        print("release:", json.dumps(out["paper"]["release"]["checks"]), flush=True)
        out = graph.resume_paper(paper_id, out["asked"]["options"][0])      # approve, or override when blocked
        print(f"[{time.perf_counter()-started:.0f}s] published: {out['status']} file={out['paper'].get('file')} counts={out['paper'].get('counts')}", flush=True)
    print("usage", out["usage"])
    oracle.close()
