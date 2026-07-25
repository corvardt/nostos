"""Serving the built interface from the same process as the API.

The frontend is a static bundle. Shipping it inside the package means an install
is one thing rather than two: no Node, no npm, no second server, and no origin
boundary between the page and the API it calls.

When the bundle is absent - a checkout that has never run the build - the API
still works and the root path says so, rather than 404ing at someone who has
done nothing wrong.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX = STATIC_DIR / "index.html"

# Vite fingerprints everything under assets/, so a changed file is a changed URL
# and none of it can go stale. Anything else keeps a short leash.
ASSET_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=300"


def is_built() -> bool:
    return INDEX.is_file()


def mount_ui(app: FastAPI) -> None:
    """Attach the built UI at the root. Call after every router is included:
    a mount at "/" matches anything left over, so it has to go last."""

    if not is_built():
        log.info("No built interface at %s; serving the API only.", STATIC_DIR)

        @app.get("/", include_in_schema=False)
        def no_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "The API is running, but the interface has not been built.",
                    "fix": "Run scripts/build-package.sh, or use the Vite dev server on :5173.",
                    "docs": "/docs",
                },
                status_code=503,
            )

        return

    root = STATIC_DIR.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """A real file is served as itself; anything else is a route inside the
        page, so it gets index.html and the client decides what it means."""
        candidate = (STATIC_DIR / path).resolve() if path else root

        # A traversal attempt resolves outside the bundle. It is not an error
        # worth naming - it simply is not a file here, and falls through to the
        # page like any other unknown path.
        if path and candidate.is_file() and candidate.is_relative_to(root):
            cache = ASSET_CACHE if path.startswith("assets/") else SHORT_CACHE
            return FileResponse(candidate, headers={"Cache-Control": cache})

        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint.")

        # index.html itself must never be cached, or a browser keeps asking for
        # the previous bundle's asset names after an upgrade.
        return FileResponse(INDEX, headers={"Cache-Control": "no-store"})
