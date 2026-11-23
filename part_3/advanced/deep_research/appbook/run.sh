#!/usr/bin/env bash
# Launch the survey paper appbook.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-}"
if [ -z "${PYTHON}" ]; then
  for candidate in ../../.venv/bin/python ../../../custom_harness/.venv/bin/python ../../../../part_2/custom_harness/.venv/bin/python; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
  PYTHON="${PYTHON:-python3}"
fi
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8041}"
echo "Survey paper appbook on http://${HOST}:${PORT}"
exec "${PYTHON}" -m uvicorn backend.main:app --host "${HOST}" --port "${PORT}" "$@"
