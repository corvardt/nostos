"""The Source contract: an account or playlist, in - Tracks, out.

Deliberately parallel to `providers.Provider`, and deliberately not the same
thing. A Provider answers "what is at this URL"; a Source answers "what songs
does this person have", with no URL involved at any point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Track


class SourceError(Exception):
    """A failure the user can act on: expired token, private playlist, typo.

    One failing source never aborts a sync - the others still run, and the
    report names the one that broke.
    """

    def __init__(self, message: str, *, needs_auth: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.needs_auth = needs_auth


class Source(ABC):
    #: Value used in a source's `type` field.
    name: str = "unknown"
    #: Human-readable, shown in the UI when adding one.
    description: str = ""
    #: Option keys that hold credentials, so the API can mask them.
    secret_options: tuple[str, ...] = ()

    def __init__(self, options: dict | None = None, label: str = "") -> None:
        self.options = options or {}
        self.label = label or self.name

    def require(self, *keys: str) -> tuple:
        """Fetch mandatory options, naming all the missing ones at once."""
        missing = [key for key in keys if not self.options.get(key)]
        if missing:
            raise SourceError(
                f"{self.label}: missing required setting(s): {', '.join(missing)}",
                needs_auth=any(key in self.secret_options for key in missing),
            )
        return tuple(self.options[key] for key in keys)

    @abstractmethod
    def fetch(self) -> list[Track]:
        """Every track this source currently holds."""
