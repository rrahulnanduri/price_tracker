from ..config import Settings
from .base import Provider, ProviderBlocked, ProviderError, ProviderNotConfigured
from .comparison import SiteProvider, sites_for
from .demo import DemoProvider
from .google_shopping import GoogleShoppingProvider
from .multi import MultiProvider
from .serpapi import SerpApiProvider

__all__ = [
    "Provider", "ProviderBlocked", "ProviderError", "ProviderNotConfigured", "build_provider",
]


def build_primary(settings: Settings, llm=None) -> Provider | None:
    """The main source. "auto" prefers SerpApi when a key is set, else the scraper; "sites" has none."""
    choice = settings.provider
    if choice == "auto":
        choice = "serpapi" if settings.serpapi_key else "google"
    if choice == "serpapi":
        return SerpApiProvider(settings.serpapi_key, settings.serpapi_seller_lookups)
    if choice == "demo":
        return DemoProvider()
    if choice == "google":
        return GoogleShoppingProvider(llm)
    if choice == "sites":
        return None
    raise ValueError(f"Unknown PRICE_PROVIDER {settings.provider!r}; use auto, google, serpapi, sites or demo.")


def build_provider(settings: Settings, llm=None) -> Provider:
    """The main source plus regional comparison sites (never mixed with made-up demo prices)."""
    primary = build_primary(settings, llm)
    if settings.provider == "demo" or not settings.comparison_sites:
        if primary is None:
            raise ValueError("PRICE_PROVIDER=sites needs COMPARISON_SITES=true.")
        return primary
    return MultiProvider(primary, lambda region: [SiteProvider(site) for site in sites_for(region)])
