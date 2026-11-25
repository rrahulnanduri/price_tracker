"""Run every price source for a region at once and pool their offers.

One failing source (blocked, down, slow) does not fail the search: its error is
reported alongside the offers the other sources found. The search fails only
if every source fails. Merging and de-duplication by shop happen later, in
`matching.select_offers`, which keeps the cheapest offer per shop whichever
source it came from.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from ..config import Region
from ..matching import Offer
from .base import Provider, ProviderBlocked, ProviderError, ProviderNotConfigured

logger = logging.getLogger(__name__)

SOURCE_TIMEOUT_SECONDS = 60


@dataclass
class SourceReport:
    name: str
    ok: bool
    offers: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "offers": self.offers, "error": self.error}


def _failure(name: str, error: BaseException) -> SourceReport:
    if isinstance(error, ProviderError):
        message = str(error)
    elif isinstance(error, asyncio.TimeoutError):
        message = "timed out"
    else:
        message = "failed"
    return SourceReport(name, ok=False, error=message)


class MultiProvider:
    def __init__(self, primary: Provider | None, extras_for: Callable[[Region], list[Provider]]):
        self.primary = primary
        self.extras_for = extras_for
        names = [primary.name] if primary else []
        self.name = "+".join(names + ["sites"]) if primary else "sites"

    def sources_for(self, region: Region) -> list[Provider]:
        return ([self.primary] if self.primary else []) + self.extras_for(region)

    async def search(self, product: str, region: Region) -> list[Offer]:
        offers, _ = await self.search_with_report(product, region)
        return offers

    async def search_with_report(
        self, product: str, region: Region, on_event: Callable[[dict], None] | None = None,
    ) -> tuple[list[Offer], list[SourceReport]]:
        """Pool every source's offers. `on_event` hears which sources start and how each one ends."""
        emit = on_event or (lambda event: None)
        sources = self.sources_for(region)
        if not sources:
            raise ProviderNotConfigured(
                f"No price source covers {region.label} in this mode. "
                "Set SERPAPI_KEY or PRICE_PROVIDER=google to search Google Shopping."
            )

        emit({"type": "sources", "names": [s.name for s in sources]})

        async def run(source: Provider):
            try:
                found = await asyncio.wait_for(source.search(product, region), SOURCE_TIMEOUT_SECONDS)
            except Exception as exc:
                emit({"type": "source", **_failure(source.name, exc).to_dict()})
                raise
            emit({"type": "source", **SourceReport(source.name, ok=True, offers=len(found)).to_dict()})
            return found

        results = await asyncio.gather(*(run(s) for s in sources), return_exceptions=True)
        offers: list[Offer] = []
        reports: list[SourceReport] = []
        errors: list[Exception] = []
        for source, result in zip(sources, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                errors.append(result)
                logger.warning("Source %s failed for %r: %r", source.name, product, result)
                reports.append(_failure(source.name, result))
                continue
            for offer in result:
                offer.source = offer.source or source.name
            offers.extend(result)
            reports.append(SourceReport(source.name, ok=True, offers=len(result)))

        if len(errors) == len(sources):
            # Surface the most informative failure: configuration, then blocking, then anything else.
            for kind in (ProviderNotConfigured, ProviderBlocked, ProviderError):
                for error in errors:
                    if isinstance(error, kind):
                        raise error
            raise ProviderError("All price sources failed")
        return offers, reports
