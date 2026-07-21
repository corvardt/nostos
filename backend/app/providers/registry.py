"""The Provider Resolver from the spec's architecture: URL -> Provider."""

from __future__ import annotations

from .base import Provider, ProviderError
from .instagram import InstagramProvider
from .threads import ThreadsProvider
from .youtube import YouTubeProvider

# Order matters only if two patterns overlap; today they are disjoint.
PROVIDERS: list[Provider] = [
    YouTubeProvider(),
    InstagramProvider(),
    ThreadsProvider(),
]


def resolve_provider(url: str) -> Provider:
    url = url.strip()
    if not url:
        raise ProviderError("No URL provided.")
    for provider in PROVIDERS:
        if provider.supports(url):
            return provider
    supported = ", ".join(p.name for p in PROVIDERS)
    raise ProviderError(f"No provider matched this URL. Supported platforms: {supported}.")
