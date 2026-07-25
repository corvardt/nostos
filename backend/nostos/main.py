from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, pidfile
from .library import router as library_router
from .library import store as library_store
from .routes import router
from .ui import mount_ui

# Every route the interface calls hangs off this, in development and installed.
API_PREFIX = "/api"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    library_store.init()
    config.ensure_dirs()
    pidfile.write()
    try:
        yield
    finally:
        pidfile.clear()


app = FastAPI(title="Nostos", version="0.1.0", lifespan=lifespan)

# Only the Vite dev server is ever a different origin. Once installed, the UI is
# served by this process from the same port, and no cross-origin request exists.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Everything the UI calls lives under /api, in development and once installed
# alike, so the frontend's base path is the same string in both. It also keeps
# the namespace clear for the static mount below, which claims the whole root.
app.include_router(router, prefix=API_PREFIX)
app.include_router(library_router, prefix=API_PREFIX)


@app.get("/health")
def health() -> dict[str, str]:
    """Outside the prefix on purpose: the launcher polls this to know when the
    server is up, before it knows anything else about the application."""
    return {"status": "ok", "version": app.version}


mount_ui(app)
