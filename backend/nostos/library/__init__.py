"""Library sync: whole music accounts in, a tagged local archive out.

The rest of Nostos answers "fetch what is at this URL". This answers "fetch
everything I have on Apple Music, Spotify, Deezer and YouTube, once, without
downloading anything twice".

The pieces, in the order a sync uses them:

  sources/   an account or playlist -> Tracks
  models     the Track itself, and merging the same song across platforms
  scan       what you already have on disk
  resolver   a Track -> a URL worth downloading
  provider   that URL -> a tagged file, through Nostos's existing job queue
  store      what has been seen, queued, downloaded or refused
  sync       the one pass that runs all of the above
"""

from __future__ import annotations

from .routes import router

__all__ = ["router"]
