"""Put the shared Part 3 modules on the import path.

    import sys
    sys.path.insert(0, "<repository>/part_3/_shared")
    import bootstrap  # noqa: F401
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for folder in ("workspace", "runtime"):
    location = str(ROOT / folder)
    if location not in sys.path:
        sys.path.insert(0, location)
