from ..config import Settings
from .base import Provider, ProviderBlocked, ProviderError, ProviderNotConfigured
from .demo import DemoProvider
from .google_shopping import GoogleShoppingProvider
from .serpapi import SerpApiProvider

__all__ = [
    "Provider", "ProviderBlocked", "ProviderError", "ProviderNotConfigured", "build_provider",
]


def build_provider(settings: Settings, llm=None) -> Provider:
    """Pick the price source. "auto" prefers SerpApi when a key is set, else the scraper."""
    choice = settings.provider
    if choice == "auto":
        choice = "serpapi" if settings.serpapi_key else "google"
    if choice == "serpapi":
        return SerpApiProvider(settings.serpapi_key)
    if choice == "demo":
        return DemoProvider()
    if choice == "google":
        return GoogleShoppingProvider(llm)
    raise ValueError(f"Unknown PRICE_PROVIDER {settings.provider!r}; use auto, google, serpapi or demo.")
