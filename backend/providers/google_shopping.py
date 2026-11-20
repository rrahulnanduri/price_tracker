"""Google Shopping scraper (no API key needed, but fragile and rate-limited by Google).

Prices are located by regex rather than CSS class, since Google's class names
change often. The offer "card" around a price is found by a known class when
it is present and otherwise structurally: the nearest ancestor that holds a
link and a product title. Every offer on the page is returned; deciding which
ones are the searched product is the job of `backend.matching`.
"""

import re
import urllib.parse

from ..config import Region
from ..matching import Offer
from ..pricing import PRICE_PATTERN, parse_price
from .base import (
    ProviderBlocked,
    ProviderError,
    ProviderNotConfigured,
    mentions_delivery,
    parse_shipping,
    parse_stock,
)

GOOGLE = "https://www.google.com"
CARD_CLASSES = ("mnr-c", "sh-dgr__content", "sh-dlr__list-result")
STORE_SELECTORS = ("div.UsGWMe", "div.aULzUe", "span.WJMUdc")
TITLE_TAGS = ("h3", "h4")
TITLE_MAX_LENGTH = 120
MAX_CARD_DEPTH = 8          # how far above a price to look for its card
MAX_PRICE_TEXT = 30         # "$1,299.00" or "From €12,99", not a paragraph
MAX_CARD_TEXT = 600         # a "card" with more text than this is a whole results column

_STARTS_LIKE_PRICE = re.compile(r"^[\W\d]")
_BLOCK_MARKERS = ("unusual traffic", "/sorry/", "recaptcha", "captcha-form")
_CONSENT_MARKERS = ("consent.google", "before you continue to google")


def build_search_url(product: str, region: Region) -> str:
    query = urllib.parse.urlencode(
        {"q": product, "tbm": "shop", "gl": region.gl, "hl": region.hl, "num": 40}
    )
    return f"{GOOGLE}/search?{query}"


def resolve_link(href: str) -> str:
    """Unwrap Google's /url? redirect and make relative links absolute."""
    if href.startswith("/url?"):
        target = re.search(r"[?&](?:url|q)=(https?[^&]+)", href)
        return urllib.parse.unquote(target.group(1)) if target else GOOGLE + href
    if href.startswith("/"):
        return GOOGLE + href
    return href


def _text(el) -> str:
    return (el.text or "").strip()


def _all_text(el) -> str:
    return el.get_all_text(separator=" | ", strip=True)


def _has_class(el, names: tuple[str, ...]) -> bool:
    classes = (el.attrib.get("class") or "").split()
    return any(name in classes for name in names)


def _find_card(price_el):
    """The element wrapping one offer: known class first, structure second."""
    card = price_el.find_ancestor(lambda el: _has_class(el, CARD_CLASSES))
    if card:
        return card
    for depth, ancestor in enumerate(price_el.iterancestors()):
        if depth >= MAX_CARD_DEPTH or ancestor.tag in ("body", "html"):
            break
        if ancestor.find("a") and _find_title(ancestor, store=None):
            # Several headings or a wall of text means this is the results list, not one card.
            headings = sum(len(ancestor.find_all(tag)) for tag in TITLE_TAGS)
            if headings > 1 or len(_all_text(ancestor)) > MAX_CARD_TEXT:
                return None
            return ancestor
    return None


def _find_title(card, store: str | None) -> str | None:
    for tag in TITLE_TAGS:
        for el in card.find_all(tag):
            if len(_text(el)) > 8:
                return _text(el)
    for el in card.css("[role=heading], [aria-level]"):
        if len(_text(el)) > 8:
            return _text(el)
    for tag in ("div", "span", "a"):
        for el in card.find_all(tag):
            text = _text(el)
            if len(text) > 15 and not _STARTS_LIKE_PRICE.search(text) and text != store:
                return text
    return None


def _find_store(card, title: str | None) -> str | None:
    for selector in STORE_SELECTORS:
        for el in card.css(selector):
            if _text(el):
                return _text(el)
    # Fallback: a short, digit-free text that is not the title is most likely the merchant.
    for tag in ("div", "span"):
        for el in card.find_all(tag):
            text = _text(el)
            if 2 < len(text) < 35 and not re.search(r"\d", text) and text != title:
                if not parse_shipping(text, "USD") == 0 and parse_stock(text) is None:
                    return text
    return None


def _find_link(card) -> str:
    for anchor in card.find_all("a"):
        href = anchor.attrib.get("href", "")
        if href and not href.startswith("#"):
            return resolve_link(href)
    return ""


def check_not_blocked(page) -> None:
    """Raise if Google served a bot check or consent wall instead of results."""
    url = (getattr(page, "url", "") or "").lower()
    html = (getattr(page, "html_content", "") or "")[:200_000].lower()
    if getattr(page, "status", 200) == 429 or any(m in url or m in html for m in _BLOCK_MARKERS):
        raise ProviderBlocked("Google is rate-limiting this address. Wait a while or use the SerpApi provider.")
    if any(m in url or m in html for m in _CONSENT_MARKERS) and "tbm=shop" not in url:
        raise ProviderBlocked("Google returned a consent page instead of results.")


def extract_offers(page, region: Region) -> list[Offer]:
    """Every priced offer on a fetched results page, in page order."""
    offers: list[Offer] = []
    seen: set[tuple[str, str, float]] = set()

    for price_el in page.find_by_regex(PRICE_PATTERN, first_match=False, case_sensitive=False):
        price_text = _text(price_el)
        if len(price_text) > MAX_PRICE_TEXT or mentions_delivery(price_text):
            continue    # a sentence that mentions a price, or a shipping fee: not the item price
        price = parse_price(price_text, region.currency)
        # A price in another currency cannot be compared with the rest.
        if price is None or price.currency != region.currency:
            continue

        card = _find_card(price_el)
        if not card:
            continue
        store = _find_store(card, _find_title(card, store=None))
        title = _find_title(card, store)
        if not store or not title:
            continue

        key = (store.upper(), title, price.value)
        if key in seen:
            continue
        seen.add(key)

        card_text = _all_text(card).replace(price_text, "", 1)
        offers.append(Offer(
            store=store.upper(),
            title=title[:TITLE_MAX_LENGTH],
            price=price.value,
            price_text=price_text,
            url=_find_link(card),
            shipping_cost=parse_shipping(card_text, region.currency),
            in_stock=parse_stock(card_text),
        ))
    return offers


class GoogleShoppingProvider:
    name = "google"

    def __init__(self, llm=None):
        # Optional backend.llm.LLMHelper: reads the page when the selectors find nothing.
        self.llm = llm

    async def search(self, product: str, region: Region) -> list[Offer]:
        try:
            # Imported here so the rest of the backend loads without a browser install.
            from scrapling.fetchers import StealthyFetcher
        except ImportError as exc:
            raise ProviderNotConfigured(
                'Scrapling is not installed. Run: pip install "scrapling[fetchers]" && scrapling install'
            ) from exc

        try:
            page = await StealthyFetcher.async_fetch(
                build_search_url(product, region), network_idle=True, locale=region.locale
            )
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                raise ProviderNotConfigured("Browser not installed. Run: scrapling install") from exc
            raise ProviderError(f"Could not load Google Shopping: {type(exc).__name__}") from exc

        check_not_blocked(page)
        offers = extract_offers(page, region)
        if not offers and self.llm is not None and self.llm.options.fallback:
            # The page loaded but nothing matched the selectors: most likely a layout change.
            from ..llm import page_text

            html = getattr(page, "html_content", "") or ""
            offers = await self.llm.extract_offers(page_text(html), product, region)
        return offers
