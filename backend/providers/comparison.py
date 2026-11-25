"""Regional price-comparison sites as extra sources.

Comparison sites list shops that are not on Google Shopping, so they widen
coverage. Each site here was checked to (a) serve its pages to a plain HTTP
client that identifies itself honestly, and (b) allow its search and product
pages in robots.txt. Sites that block non-browser clients are deliberately left
out rather than disguised as a browser.

Most of the work is generic: product pages publish their sellers as schema.org
`Offer` data (JSON-LD), which `schema_offers` reads without any site-specific
selectors. A site only has to say how to search and how to find product pages
in its results.
"""

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ..config import Region
from ..matching import Offer, score_relevance
from ..pricing import parse_price
from .base import ProviderBlocked, ProviderError

logger = logging.getLogger(__name__)

USER_AGENT = "PriceTracker/1.0 (personal price comparison; +https://github.com/rrahulnanduri/price_tracker)"
TIMEOUT_SECONDS = 15
PRODUCT_PAGES_PER_SITE = 3       # product pages opened per search, best matches first
MIN_PRODUCT_MATCH = 0.5          # a results-page title must score this to be worth opening
POLITE_DELAY_SECONDS = 1.0       # between requests to the same site (robots.txt crawl-delay)


# -- generic schema.org reader ---------------------------------------------------

def _json_ld_blocks(html: str) -> list:
    blocks = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            blocks.append(json.loads(raw.strip()))
        except ValueError:
            continue
    return blocks


def _walk(node):
    """Every dict inside a JSON-LD block, including @graph members."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _types(node: dict) -> set[str]:
    kind = node.get("@type", "")
    return set(kind) if isinstance(kind, list) else {kind}


def _shipping(offer: dict) -> float | None:
    details = offer.get("shippingDetails")
    for detail in details if isinstance(details, list) else [details]:
        if isinstance(detail, dict):
            rate = detail.get("shippingRate") or {}
            value = rate.get("value") if isinstance(rate, dict) else None
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _stock(offer: dict) -> bool | None:
    availability = str(offer.get("availability") or "").lower()
    if not availability:
        return None
    return not any(word in availability for word in ("outofstock", "soldout", "discontinued"))


def _condition(offer: dict) -> str:
    condition = str(offer.get("itemCondition") or "").lower()
    if "refurbished" in condition:
        return "refurbished"
    if "used" in condition or "damaged" in condition:
        return "used"
    return "new"


def schema_offers(html: str, region: Region, base_url: str = "", source: str = "") -> list[Offer]:
    """Sellers listed on a product page as schema.org Product -> offers."""
    offers: list[Offer] = []
    for block in _json_ld_blocks(html):
        for node in _walk(block):
            if not _types(node) & {"Product", "ProductGroup"}:
                continue
            title = str(node.get("name") or "").strip()
            entries = node.get("offers")
            entries = entries if isinstance(entries, list) else [entries]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # An AggregateOffer may nest the individual offers.
                individual = entry.get("offers") if "AggregateOffer" in _types(entry) else [entry]
                for item in individual if isinstance(individual, list) else []:
                    offer = _offer_from_schema(item, title, region, base_url, source)
                    if offer:
                        offers.append(offer)
    return offers


def _offer_from_schema(item: dict, title: str, region: Region, base_url: str, source: str) -> Offer | None:
    if not isinstance(item, dict):
        return None
    seller = item.get("seller")
    store = (seller.get("name") if isinstance(seller, dict) else seller) or ""
    currency = str(item.get("priceCurrency") or region.currency).upper()
    price_value = item.get("price")
    if not store or not title or currency != region.currency or price_value in (None, ""):
        return None
    price = parse_price(f"{price_value} {currency}", region.currency)
    if price is None:
        return None
    url = urllib.parse.urljoin(base_url, str(item.get("url") or "")) if item.get("url") else base_url
    offer = Offer(
        store=str(store).strip().upper(),
        title=title[:120],
        price=price.value,
        price_text=f"{price.value:,.2f} {currency}",
        url=url,
        shipping_cost=_shipping(item),
        in_stock=_stock(item),
        source=source,
    )
    if _condition(item) != "new":
        offer.title = f"{offer.title} ({_condition(item)})"
    return offer


# -- sites ---------------------------------------------------------------------

@dataclass(frozen=True)
class Site:
    name: str
    regions: frozenset[str]
    search_url: str                                     # {q} = query, form-encoded
    # (results page html, page url, query, region) -> offers listed directly on the page
    parse_results: Callable[[str, str, str, Region], list[Offer]] | None = None
    # (results page html, page url) -> [(title, product page url)]
    find_products: Callable[[str, str], list[tuple[str, str]]] | None = None


KIESKEURIG_HOSTS = frozenset({"www.kieskeurig.nl", "www.kieskeurig.be"})


def same_site(url: str, hosts: frozenset[str]) -> bool:
    """True for an https URL on one of the site's own hosts. Product links found on a page are
    fetched by the backend, so a link elsewhere (e.g. protocol-relative "//other.host/...") is skipped."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and parts.hostname in hosts and parts.port is None


def kieskeurig_products(html: str, page_url: str) -> list[tuple[str, str]]:
    """Product pages in a results page, titled by their best link text or else their URL slug."""
    titles: dict[str, str] = {}
    pattern = r'<a[^>]+href="((?:https://www\.kieskeurig\.(?:nl|be))?/[^"]*/product/\d+-[^"#?]+)"[^>]*>(.*?)</a>'
    for href, text in re.findall(pattern, html, re.S):
        url = urllib.parse.urljoin(page_url, href)
        if not same_site(url, KIESKEURIG_HOSTS):
            continue
        slug = href.rsplit("/", 1)[-1].split("-", 1)[-1].replace("-", " ")
        text = html_lib.unescape(re.sub(r"<[^>]+>|\s+", " ", text)).strip()
        # Many links say only "Bekijk product" or wrap an image; the slug names the product.
        best = text if len(text.split()) >= 2 and fold_words(text) & fold_words(slug) else slug
        if len(best) > len(titles.get(url, "")):
            titles[url] = best
    return list((title, url) for url, title in titles.items())


def fold_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


_STATICICE_ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>\s*<a[^>]+>\s*\$([\d,]+\.\d{2})\s*</a>.*?</tr>", re.S | re.I
)


def staticice_offers(html: str, page_url: str, query: str, region: Region) -> list[Offer]:
    offers = []
    for row in _STATICICE_ROW.finditer(html):
        block = row.group(0)
        links = re.findall(r'href="(/cgi-bin/redirect\.cgi\?[^"]+)"', block)
        if not links:
            continue
        params = urllib.parse.parse_qs(urllib.parse.urlparse(links[0].replace("&amp;", "&")).query)
        store = (params.get("name") or [""])[0]
        shop_url = (params.get("newurl") or [""])[0]   # link straight to the shop, not the redirector
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)
        # The description is the second cell, up to the line break before the shop details.
        description = re.split(r"<br", cells[1], maxsplit=1, flags=re.I)[0] if len(cells) > 1 else ""
        title = html_lib.unescape(re.sub(r"<[^>]+>|\s+", " ", description)).strip()
        title = re.sub(r"^\[[^\]]*\]\s*", "", title)   # drop "[SKU123]" prefixes
        price = parse_price(f"${row.group(1)}", region.currency)
        if store and title and price and shop_url.startswith("http"):
            offers.append(Offer(store.upper(), title[:120], price.value, f"${row.group(1)}", shop_url,
                                source="staticice"))
    return offers


SITES = [
    Site("kieskeurig", frozenset({"NL"}), "https://www.kieskeurig.nl/search?q={q}",
         find_products=kieskeurig_products),
    Site("kieskeurig", frozenset({"BE"}), "https://www.kieskeurig.be/search?q={q}",
         find_products=kieskeurig_products),
    Site("staticice", frozenset({"AU"}), "https://www.staticice.com.au/cgi-bin/search.cgi?q={q}",
         parse_results=staticice_offers),
]


def sites_for(region: Region) -> list[Site]:
    return [site for site in SITES if region.code in site.regions]


# -- provider ------------------------------------------------------------------

class SiteProvider:
    """One comparison site as a price source."""

    def __init__(self, site: Site, client_factory=None):
        self.site = site
        self.name = site.name
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS, follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "nl,en;q=0.8"},
        ))

    async def _get(self, client, url: str) -> str:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: could not connect ({type(exc).__name__})") from exc
        if response.status_code in (403, 405, 429):
            raise ProviderBlocked(f"{self.name}: refused the request ({response.status_code})")
        if response.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {response.status_code}")
        return response.text

    async def search(self, product: str, region: Region) -> list[Offer]:
        url = self.site.search_url.format(q=urllib.parse.quote_plus(product))
        async with self._client_factory() as client:
            html = await self._get(client, url)
            if self.site.parse_results:
                return self.site.parse_results(html, url, product, region)

            candidates = self.site.find_products(html, url) if self.site.find_products else []
            scored = sorted(
                ((score_relevance(product, title)[0], title, link) for title, link in candidates),
                key=lambda row: -row[0],
            )
            chosen = [link for score, _, link in scored if score >= MIN_PRODUCT_MATCH][:PRODUCT_PAGES_PER_SITE]
            offers: list[Offer] = []
            for index, link in enumerate(chosen):
                if index:
                    await asyncio.sleep(POLITE_DELAY_SECONDS)
                try:
                    page = await self._get(client, link)
                except ProviderError as exc:
                    logger.info("Skipping product page %s: %s", link, exc)
                    continue
                offers.extend(schema_offers(page, region, base_url=link, source=self.name))
            return offers
