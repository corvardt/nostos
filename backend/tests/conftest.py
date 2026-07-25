"""Point the app at a throwaway data directory before anything imports config."""

from __future__ import annotations

import os
import tempfile

# app.config reads this at import time, so it must be set before the first
# `import nostos.*` anywhere in the suite. conftest is imported first.
os.environ.setdefault("NOSTOS_DATA_DIR", tempfile.mkdtemp(prefix="nostos-tests-"))
