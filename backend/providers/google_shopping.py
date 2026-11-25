"""Google Shopping scraper (no API key needed, but fragile and rate-limited by Google).

Prices are located by regex rather than CSS class, since Google's class names
change often. The offer "card" around a price is found by a known class when
it is present and otherwise structurally: the nearest ancestor that holds a
link and a product title. Every offer on the page is returned; deciding which
ones are the searched product is the job of `backend.matching`.
"""

import asyncio
import os
import re
import sys
import urllib.parse

from ..config import Region
from ..matching import Offer, safe_url
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
TITLE_MAX_LENGTH = 120
MAX_CARD_DEPTH = 8          # how far above a price to look for its card
MAX_PRICE_TEXT = 30         # "$1,299.00" or "From €12,99", not a paragraph
MAX_CARD_TEXT = 600         # a "card" with more text than this is a whole results column

# Checked against the address only: normal results pages mention "/sorry/index" and
# "consent.google" in their own scripts, so finding them in the page text proves nothing.
_BLOCK_URL_MARKERS = ("/sorry/",)
_CONSENT_URL_MARKERS = ("consent.google",)
# Visible wording of the bot check and the consent wall, which results pages do not contain.
_BLOCK_TEXT_MARKERS = ("unusual traffic", 'id="captcha-form"')
_CONSENT_TEXT_MARKERS = ("before you continue to google",)


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


# Short texts on an offer card that are labels, not the shop's name.
_LABELS = {
    # condition
    "pre-owned", "preowned", "used", "refurbished", "renewed", "open box", "tweedehands", "gebruikt",
    "gebraucht", "generalüberholt", "generaluberholt", "erneuert", "occasion", "reconditionné", "reacondicionado",
    "usato", "ricondizionato", "begagnad", "new", "nieuw", "neu", "neuf", "nuevo", "nuovo", "ny",
    # more sellers / offers
    "& more", "and more", "more prices", "& more prices", "en meer", "& meer prijzen", "meer prijzen",
    "und mehr", "& mehr preise", "et plus", "et plus de prix", "& plus de prix", "y más", "e altro", "med mera",
    # promotions and badges
    "sale", "on sale", "price drop", "in de uitverkoop", "uitverkoop", "aanbieding", "prijsdaling",
    "angebot", "promo", "soldes", "oferta", "offerta", "rea", "sponsored", "gesponsord", "anzeige",
    "sponsorisé", "patrocinado", "sponsorizzato", "popular", "populair", "best seller", "bestseller",
    # availability and pick-up
    "in stock", "op voorraad", "in store", "in winkel", "nearby", "ook in de buurt", "in der nähe",
    "pick up today", "vandaag ophalen", "out of stock", "niet op voorraad",
}
_CONDITION_LABELS = {
    "pre-owned": "Pre-owned", "preowned": "Pre-owned", "used": "Used", "refurbished": "Refurbished",
    "renewed": "Refurbished", "open box": "Open box", "tweedehands": "Tweedehands", "gebruikt": "Used",
    "gebraucht": "Gebraucht", "generalüberholt": "Refurbished", "generaluberholt": "Refurbished",
    "erneuert": "Refurbished",
    "occasion": "Occasion", "reconditionné": "Refurbished", "reacondicionado": "Refurbished",
    "usato": "Usato", "ricondizionato": "Refurbished", "begagnad": "Begagnad",
}
_NOT_A_SHOP = re.compile(
    r"\d[.,]\d\b|^\(?\d|deliver|delivery|shipping|bezorg|levering|verzend|retour|return|versand|lieferung"
    r"|livraison|envío|envio|spedizione|frakt|ophalen|pick ?up|dagen|days|rating|review|beoordel",
    re.IGNORECASE,
)
# Money that is not the offer's price: a struck-out "Was ₹1,354" or a converted "(AED 1,323)".
_OTHER_MONEY = re.compile(r"[$€£¥₹]\s?\d|^\s*\(?\s*(?:was|vorher|avant|antes|prima|eerder|voorheen)\b",
                          re.IGNORECASE)
_CURRENCY_CODE_AMOUNT = re.compile(r"\b[A-Z]{3}\s?\d")   # case-sensitive, so "Shop 24" is not caught
MIN_TITLE_LENGTH = 8
_PRICE_FILTER = re.compile(
    r"\b(?:under|over|below|above|up to|max(?:imaal|imum)?|min(?:imaal|imum)?|meer dan|minder dan|tot|onder"
    r"|boven|bis|unter|über|moins de|plus de|hasta|fino a)\b|\d\s*[-–]\s*\D{0,3}\d",
    re.IGNORECASE,
)


def _is_price(segment: str, currency: str) -> bool:
    match = re.fullmatch(rf"\s*(?:from|vanaf|ab|à partir de|desde|da)?\s*(?:{PRICE_PATTERN})\s*",
                         segment, re.IGNORECASE)
    return bool(match) and parse_price(segment, currency) is not None


def _is_other_money(segment: str) -> bool:
    """A struck-out or converted price, which must not be read as the shop's name."""
    return bool(_OTHER_MONEY.search(segment) or _CURRENCY_CODE_AMOUNT.search(segment))


def parse_card_text(segments: list[str], currency: str) -> dict | None:
    """Read an offer card's text pieces into {title, store, condition}, or None if it is not an offer.

    Works on any layout that shows a title, a price and a shop as separate pieces of text,
    in whatever order: the title is the first long piece; the shop is the first short piece
    that is not the title, a price, a label ("Pre-owned", "& more"), a delivery note or a rating.
    """
    pieces = [" ".join(seg.split()) for seg in segments]
    pieces = [seg for seg in pieces if seg]
    title = store = None
    condition = None
    for seg in pieces:
        folded = seg.lower().strip(" .·•")
        if folded in _CONDITION_LABELS:
            condition = condition or _CONDITION_LABELS[folded]
            continue
        if folded in _LABELS or _is_price(seg, currency) or mentions_delivery(seg):
            continue
        if re.search(r"\d", seg) and _PRICE_FILTER.search(seg):
            continue   # a price-filter chip ("Under $200", "Meer dan € 200"), not an offer
        if title is None:
            if len(seg) >= MIN_TITLE_LENGTH and re.search(r"[^\W\d_]{3}", seg):
                title = seg
            continue
        if (store is None and 2 <= len(seg) <= 50 and seg != title
                and not _NOT_A_SHOP.search(seg) and not _is_other_money(seg)):
            store = seg
            break
    if not title or not store:
        return None
    return {"title": title, "store": store, "condition": condition}


def _segments(el) -> list[str]:
    return el.get_all_text(separator="\n", strip=True).split("\n")


def _find_card(price_el, currency: str):
    """The element wrapping one offer and its parsed text: known class first, structure second."""
    card = price_el.find_ancestor(lambda el: _has_class(el, CARD_CLASSES))
    if card is not None:
        parsed = parse_card_text(_segments(card), currency)
        if parsed:
            return card, parsed
    for depth, ancestor in enumerate(price_el.iterancestors()):
        if depth >= MAX_CARD_DEPTH or ancestor.tag in ("body", "html"):
            break
        if len(_all_text(ancestor)) > MAX_CARD_TEXT:
            break   # grown past one offer into a whole column of results
        parsed = parse_card_text(_segments(ancestor), currency)
        if parsed:
            return ancestor, parsed
    return None, None


def _find_link(card) -> str:
    for anchor in card.find_all("a"):
        href = anchor.attrib.get("href", "")
        if href and not href.startswith("#") and (link := safe_url(resolve_link(href))):
            return link
    return ""


def check_not_blocked(page) -> None:
    """Raise if Google served a bot check or consent wall instead of results."""
    url = (getattr(page, "url", "") or "").lower()
    html = (getattr(page, "html_content", "") or "")[:200_000].lower()
    if (getattr(page, "status", 200) == 429 or any(m in url for m in _BLOCK_URL_MARKERS)
            or any(m in html for m in _BLOCK_TEXT_MARKERS)):
        raise ProviderBlocked("Google is rate-limiting this address. Wait a while or use the SerpApi provider.")
    if any(m in url for m in _CONSENT_URL_MARKERS):
        raise ProviderBlocked("Google returned a consent page instead of results.")


def check_consent_wall(page) -> None:
    """Raise if a page with no offers was a consent wall. Only asked when nothing was found:
    Google often lays its consent dialog over a full results page, which is still readable."""
    html = (getattr(page, "html_content", "") or "").lower()
    if any(m in html for m in _CONSENT_TEXT_MARKERS):
        raise ProviderBlocked("Google returned a consent page instead of results.")


def extract_offers(page, region: Region) -> list[Offer]:
    """Every priced offer on a fetched results page, in page order."""
    offers: list[Offer] = []
    seen: set[tuple[str, str, float]] = set()

    for price_el in page.find_by_regex(PRICE_PATTERN, first_match=False, case_sensitive=False):
        price_text = _text(price_el)
        if len(price_text) > MAX_PRICE_TEXT or mentions_delivery(price_text) or _PRICE_FILTER.search(price_text):
            # A sentence that mentions a price, a shipping fee, or a price-filter chip
            # ("Under $200", "$200 - $500"): not an item price.
            continue
        price = parse_price(price_text, region.currency)
        # A price in another currency cannot be compared with the rest.
        if price is None or price.currency != region.currency:
            continue

        card, parsed = _find_card(price_el, region.currency)
        if card is None:
            continue
        store, title = parsed["store"], parsed["title"]
        if parsed["condition"]:
            # In the title, so matching treats a used or refurbished unit as such.
            title = f'{title} ({parsed["condition"]})'

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
            # Newer layouts open offers through script, not links: fall back to a search for the item.
            url=_find_link(card) or build_search_url(parsed["title"], region),
            shipping_cost=parse_shipping(card_text, region.currency),
            in_stock=parse_stock(card_text),
        ))
    return offers


EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def fallback_browser() -> str | None:
    """A system browser to use when the bundled one cannot start: SCRAPER_BROWSER_PATH, else Edge on Windows."""
    configured = os.environ.get("SCRAPER_BROWSER_PATH", "").strip()
    if configured:
        return configured if os.path.isfile(configured) else None
    if sys.platform == "win32":
        return next((path for path in EDGE_PATHS if os.path.isfile(path)), None)
    return None


async def fetch_page(fetcher, url: str, locale: str, executable_path: str | None = None):
    """Load a page in the stealth browser.

    On Windows, starting a browser needs a Proactor event loop, but uvicorn runs
    on a Selector loop when auto-reload is on, where it fails with
    NotImplementedError. In that case the fetch runs on its own Proactor loop
    in a worker thread.
    """
    kwargs = {"network_idle": True, "locale": locale}
    if executable_path:
        kwargs["executable_path"] = executable_path
    proactor = getattr(asyncio, "ProactorEventLoop", None)
    if sys.platform == "win32" and proactor and not isinstance(asyncio.get_running_loop(), proactor):
        def run_on_proactor():
            loop = proactor()
            try:
                return loop.run_until_complete(fetcher.async_fetch(url, **kwargs))
            finally:
                loop.close()

        return await asyncio.to_thread(run_on_proactor)
    return await fetcher.async_fetch(url, **kwargs)


def _cannot_start(exc: Exception) -> bool:
    text = str(exc)
    return "spawn UNKNOWN" in text or "Executable doesn't exist" in text


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
            url = build_search_url(product, region)
            try:
                page = await fetch_page(StealthyFetcher, url, region.locale)
            except Exception as exc:
                # Locked-down machines often block the downloaded browser but allow the system one.
                browser = fallback_browser()
                if browser and _cannot_start(exc):
                    page = await fetch_page(StealthyFetcher, url, region.locale, executable_path=browser)
                else:
                    raise
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                raise ProviderNotConfigured("Browser not installed. Run: scrapling install") from exc
            if "spawn UNKNOWN" in str(exc):
                raise ProviderNotConfigured(
                    "The scraper's browser could not start on this computer (Windows refused to run it)."
                ) from exc
            first_line = (str(exc).strip().splitlines() or [""])[0][:140]
            detail = f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__
            raise ProviderError(f"Could not load Google Shopping: {detail}") from exc

        check_not_blocked(page)
        offers = extract_offers(page, region)
        if not offers:
            check_consent_wall(page)
        if not offers and self.llm is not None and self.llm.options.fallback:
            # The page loaded but nothing matched the selectors: most likely a layout change.
            from ..llm import page_text

            html = getattr(page, "html_content", "") or ""
            offers = await self.llm.extract_offers(page_text(html), product, region)
        return offers
