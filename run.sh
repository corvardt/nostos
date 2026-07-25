#!/usr/bin/env bash
# Start the Nostos backend (:8000) and frontend dev server (:5173) together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/backend/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "Creating backend virtualenv…"
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install -q -e "$ROOT/backend"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies…"
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit)
fi

# Stop both halves when this script is interrupted.
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && PYTHONPATH=. "$VENV/bin/uvicorn" nostos.main:app --port 8000 --reload) &
pids+=($!)

(cd "$ROOT/frontend" && npm run dev) &
pids+=($!)

echo
echo "  backend  -> http://127.0.0.1:8000"
echo "  frontend -> http://localhost:5173"
echo
wait
