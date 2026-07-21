"""The Provider contract from the POC spec.

    interface Provider {
      supports(url: string): boolean;
      resolve(url: string): Promise<MediaInfo>;
      download(url: string, format?: string): Promise<string>;
    }

Every platform integration implements this and nothing else, so the resolver, the
download manager and the API layer never learn platform-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..models import MediaInfo

ProgressCallback = Callable[[dict], None]


class ProviderError(Exception):
    """A failure the user can act on (bad URL, private post, login required)."""

    def __init__(self, message: str, *, needs_auth: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.needs_auth = needs_auth


class Provider(ABC):
    name: str = "unknown"

    @abstractmethod
    def supports(self, url: str) -> bool:
        """True if this provider can handle the URL."""

    @abstractmethod
    def resolve(self, url: str) -> MediaInfo:
        """Fetch metadata without downloading."""

    @abstractmethod
    def download(
        self,
        url: str,
        fmt: str | None = "best",
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Download the media and return the resulting file path."""
