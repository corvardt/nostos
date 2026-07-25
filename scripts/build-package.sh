#!/usr/bin/env bash
# Build the interface into the Python package, so that installing the backend
# installs the frontend too.
#
# The output is gitignored, so run this before building a wheel, and any time
# you want to check the bundled UI rather than the Vite dev server.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/backend/nostos/static"

command -v npm >/dev/null || { echo "npm is required to build the interface." >&2; exit 1; }

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies…"
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit)
fi

echo "Building the interface…"
(cd "$ROOT/frontend" && npm run build)

# Replace rather than merge: a stale asset from a previous build would be dead
# weight in the wheel, and Vite's filenames are content-hashed, so nothing here
# is ever worth keeping.
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$ROOT/frontend/dist/." "$DEST/"

echo "Bundled into backend/nostos/static ($(du -sh "$DEST" | cut -f1))"
