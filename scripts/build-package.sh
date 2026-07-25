#!/usr/bin/env bash
# Assemble everything the Python package needs that is not Python: the built
# interface, and the readme that becomes the PyPI page.
#
# Both are generated and gitignored, so run this before building a wheel, and
# any time you want to check the bundled UI rather than the Vite dev server.
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

# A real copy, not a symlink. A symlink works for the wheel, whose metadata is
# read at build time, but lands in the sdist as a link pointing outside the
# archive, which pip refuses to extract. Copying keeps one source of truth
# without asking the tarball to carry something it cannot.
cp "$ROOT/README.md" "$ROOT/backend/README.md"

echo "Bundled into backend/nostos/static ($(du -sh "$DEST" | cut -f1)), readme copied."
