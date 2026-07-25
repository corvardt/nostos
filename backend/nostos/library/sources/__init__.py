"""Source registry: a `type` string to the class that implements it."""

from __future__ import annotations

from .apple import AppleMusicSource
from .base import Source, SourceError
from .deezer import DeezerSource
from .jsonfile import JsonFileSource
from .spotify import SpotifySource
from .youtube import YouTubeSource

SOURCES: tuple[type[Source], ...] = (
    AppleMusicSource,
    SpotifySource,
    DeezerSource,
    YouTubeSource,
    JsonFileSource,
)

REGISTRY: dict[str, type[Source]] = {cls.name: cls for cls in SOURCES}


def build_source(kind: str, options: dict | None = None, label: str = "") -> Source:
    cls = REGISTRY.get(kind)
    if cls is None:
        raise SourceError(
            f"Unknown source type {kind!r}. Available: {', '.join(sorted(REGISTRY))}."
        )
    return cls(options, label)


def catalog() -> list[dict]:
    """What the UI needs to offer a choice of source types."""
    return [
        {"type": cls.name, "description": cls.description, "secrets": list(cls.secret_options)}
        for cls in SOURCES
    ]


__all__ = ["REGISTRY", "SOURCES", "Source", "SourceError", "build_source", "catalog"]
