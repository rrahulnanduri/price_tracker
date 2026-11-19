"""Regions and environment-driven settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    code: str
    gl: str
    hl: str
    currency: str
    label: str
    locale: str


DEFAULT_REGION = "US"

_REGION_ROWS = [
    # code, gl, hl, currency, label, locale
    ("US", "us", "en", "USD", "United States", "en-US"),
    ("CA", "ca", "en", "CAD", "Canada", "en-CA"),
    ("GB", "gb", "en", "GBP", "United Kingdom", "en-GB"),
    ("IE", "ie", "en", "EUR", "Ireland", "en-IE"),
    ("NL", "nl", "nl", "EUR", "Netherlands", "nl-NL"),
    ("BE", "be", "nl", "EUR", "Belgium", "nl-BE"),
    ("DE", "de", "de", "EUR", "Germany", "de-DE"),
    ("AT", "at", "de", "EUR", "Austria", "de-AT"),
    ("CH", "ch", "de", "CHF", "Switzerland", "de-CH"),
    ("FR", "fr", "fr", "EUR", "France", "fr-FR"),
    ("ES", "es", "es", "EUR", "Spain", "es-ES"),
    ("IT", "it", "it", "EUR", "Italy", "it-IT"),
    ("SE", "se", "sv", "SEK", "Sweden", "sv-SE"),
    ("PL", "pl", "pl", "PLN", "Poland", "pl-PL"),
    ("IN", "in", "en", "INR", "India", "en-IN"),
    ("JP", "jp", "ja", "JPY", "Japan", "ja-JP"),
    ("SG", "sg", "en", "SGD", "Singapore", "en-SG"),
    ("AE", "ae", "en", "AED", "UAE", "en-AE"),
    ("AU", "au", "en", "AUD", "Australia", "en-AU"),
]

REGIONS: dict[str, Region] = {row[0]: Region(*row) for row in _REGION_ROWS}


def get_region(country: str | None) -> Region | None:
    """Region for a country code, or None if it is not supported."""
    return REGIONS.get((country or "").strip().upper())


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    provider: str                 # "auto" | "google" | "serpapi" | "demo"
    serpapi_key: str
    db_path: str
    cors_origins: list[str]
    cache_ttl_seconds: int        # how long a search result is reused
    rate_limit_per_minute: int    # live fetches per client; 0 disables
    max_concurrent_fetches: int
    refresh_hours: float          # watchlist re-check interval; 0 disables
    min_relevance: float          # offers scoring below this are dropped
    max_results: int
    alert_webhook_url: str


def load_settings() -> Settings:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        provider=os.environ.get("PRICE_PROVIDER", "auto").strip().lower(),
        serpapi_key=os.environ.get("SERPAPI_KEY", "").strip(),
        db_path=os.environ.get("PRICE_DB", "price_tracker.db"),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 900),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 10),
        max_concurrent_fetches=max(1, _int("MAX_CONCURRENT_FETCHES", 2)),
        refresh_hours=_float("REFRESH_HOURS", 6),
        min_relevance=_float("MIN_RELEVANCE", 0.7),
        max_results=_int("MAX_RESULTS", 8),
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", "").strip(),
    )
