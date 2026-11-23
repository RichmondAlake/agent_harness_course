"""The appbook's name for the Part 3 database module.

The code lives in ``part_3/_shared/oracle_database.py`` so that the notebook and the
appbook prepare the database the same way. This file keeps ``from shared import oracle`` working.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SHARED = next(folder / "_shared" for folder in Path(__file__).resolve().parents
               if (folder / "_shared" / "oracle_database.py").exists())
sys.path.insert(0, str(_SHARED))
import oracle_database as _database  # noqa: E402

globals().update({name: value for name, value in vars(_database).items() if not name.startswith("__")})
