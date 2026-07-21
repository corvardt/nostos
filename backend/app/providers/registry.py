"""The Provider Resolver from the spec's architecture: URL -> Provider."""

from __future__ import annotations

from .base import Provider, ProviderError
from .generic import GenericProvider
from .instagram import InstagramProvider
from .threads import ThreadsProvider
from .youtube import YouTubeProvider

# Order matters: the dedicated providers claim their URLs first, and the
# generic yt-dlp fallback sweeps up whatever is left.
PROVIDERS: list[Provider] = [
    YouTubeProvider(),
    InstagramProvider(),
    ThreadsProvider(),
    GenericProvider(),
]

# The ones with platform-specific handling, named in errors and docs.
NAMED = [p.name for p in PROVIDERS if p.name != "generic"]


def resolve_provider(url: str) -> Provider:
    url = url.strip()
    if not url:
        raise ProviderError("No URL provided.")
    for provider in PROVIDERS:
        if provider.supports(url):
            return provider
    raise ProviderError(
        "That does not look like a link. Paste a full URL starting with http:// or https://."
    )
