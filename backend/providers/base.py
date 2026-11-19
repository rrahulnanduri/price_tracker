"""What every price source has to provide, plus helpers they share."""

import re
from typing import Protocol

from ..config import Region
from ..matching import Offer, fold
from ..pricing import find_marked_price


class ProviderError(Exception):
    """The source could not be reached or returned something unusable."""


class ProviderBlocked(ProviderError):
    """The source refused the request (bot check, consent wall, quota)."""


class ProviderNotConfigured(ProviderError):
    """The source needs setup that is missing (API key, browser install)."""


class Provider(Protocol):
    name: str

    async def search(self, product: str, region: Region) -> list[Offer]:
        """Every offer found for the product, unfiltered and unranked."""
        ...


_FREE_DELIVERY = (
    "free delivery", "free shipping", "free postage", "gratis verzending", "gratis bezorging",
    "kostenloser versand", "kostenlose lieferung", "versandkostenfrei", "livraison gratuite",
    "livraison offerte", "envio gratis", "spedizione gratuita", "fri frakt", "darmowa dostawa",
)
_DELIVERY_WORDS = (
    "delivery", "shipping", "postage", "verzending", "verzendkosten", "bezorging", "versand",
    "lieferung", "livraison", "envio", "spedizione", "frakt", "dostawa",
)
_OUT_OF_STOCK = (
    "out of stock", "sold out", "currently unavailable", "unavailable", "niet op voorraad",
    "uitverkocht", "nicht verfugbar", "nicht auf lager", "ausverkauft", "rupture de stock",
    "indisponible", "agotado", "sin stock", "non disponibile", "esaurito", "slut i lager",
)
_IN_STOCK = (
    "in stock", "op voorraad", "auf lager", "sofort lieferbar", "en stock", "disponibile",
    "i lager",
)


def parse_shipping(text: str | None, currency: str) -> float | None:
    """Shipping cost named in delivery text: 0 if free, None if not stated."""
    if not text:
        return None
    folded = fold(text)
    if any(phrase in folded for phrase in _FREE_DELIVERY):
        return 0.0
    for word in _DELIVERY_WORDS:
        # "+ $4.99 shipping" or "Delivery €3,95": a price within a few words of the term.
        near = re.search(rf"([^|]{{0,24}}){word}([^|]{{0,24}})", folded)
        if near:
            # Only a figure with a currency marker counts; "Delivery by Nov 14" is a date.
            price = find_marked_price(near.group(1), currency) or find_marked_price(near.group(2), currency)
            if price:
                return price.value
    return None


def mentions_delivery(text: str) -> bool:
    """True for delivery text such as "+ $5.99 shipping", whose figure is not the item price."""
    folded = fold(text)
    return any(word in folded for word in _DELIVERY_WORDS)


def parse_stock(text: str | None) -> bool | None:
    """False if the text says unavailable, True if it says available, else None."""
    if not text:
        return None
    folded = fold(text)
    if any(phrase in folded for phrase in _OUT_OF_STOCK):
        return False
    if any(phrase in folded for phrase in _IN_STOCK):
        return True
    return None
