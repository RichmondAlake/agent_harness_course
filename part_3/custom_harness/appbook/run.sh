#!/usr/bin/env bash
# Launch the PPA custom-harness appbook.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-}"
if [ -z "${PYTHON}" ]; then
  if [ -x "../.venv/bin/python" ]; then PYTHON="../.venv/bin/python"; else PYTHON="python3"; fi
fi

if ! "${PYTHON}" -c "import fastapi, sse_starlette, uvicorn, langgraph, langchain_mcp_adapters, aiosqlite" 2>/dev/null; then
  echo "Missing appbook dependencies for ${PYTHON}. Install them with:" >&2
  echo "  ${PYTHON} -m pip install -r requirements.txt" >&2
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8050}"
echo "PPA custom-harness appbook on http://${HOST}:${PORT}"
exec "${PYTHON}" -m uvicorn backend.main:app --host "${HOST}" --port "${PORT}" "$@"
