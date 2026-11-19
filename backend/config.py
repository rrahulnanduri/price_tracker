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


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    provider: str                 # "auto" | "google" | "serpapi" | "sites" | "demo"
    serpapi_key: str
    serpapi_seller_lookups: int   # product pages opened for their full seller list (1 SerpApi credit each)
    comparison_sites: bool        # add regional price-comparison sites as extra sources
    db_path: str
    cors_origins: list[str]
    cache_ttl_seconds: int        # how long a search result is reused
    rate_limit_per_minute: int    # live fetches per client; 0 disables
    max_concurrent_fetches: int
    refresh_hours: float          # watchlist re-check interval; 0 disables
    min_relevance: float          # offers scoring below this are dropped
    max_results: int
    alert_webhook_url: str
    llm_model: str                # "provider/model" for ScrapeGraphAI; empty disables AI help
    llm_api_key: str
    llm_base_url: str             # e.g. a local Ollama server
    llm_model_tokens: int         # context size, needed for models ScrapeGraphAI does not know
    llm_fallback: bool            # let the LLM read pages the scraper's selectors cannot
    llm_judge: bool               # let the LLM give a second opinion on which listings match


def load_settings() -> Settings:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        provider=os.environ.get("PRICE_PROVIDER", "auto").strip().lower(),
        serpapi_key=os.environ.get("SERPAPI_KEY", "").strip(),
        serpapi_seller_lookups=max(0, _int("SERPAPI_SELLER_LOOKUPS", 2)),
        comparison_sites=_bool("COMPARISON_SITES", True),
        db_path=os.environ.get("PRICE_DB", "price_tracker.db"),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 900),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 10),
        max_concurrent_fetches=max(1, _int("MAX_CONCURRENT_FETCHES", 2)),
        refresh_hours=_float("REFRESH_HOURS", 6),
        min_relevance=_float("MIN_RELEVANCE", 0.7),
        max_results=_int("MAX_RESULTS", 50),
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "").strip(),
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_base_url=os.environ.get("LLM_BASE_URL", "").strip(),
        llm_model_tokens=_int("LLM_MODEL_TOKENS", 0),
        llm_fallback=_bool("LLM_FALLBACK", True),
        llm_judge=_bool("LLM_JUDGE", True),
    )
