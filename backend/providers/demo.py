"""Made-up prices for developing the UI and running evals without the network.

Enabled only with PRICE_PROVIDER=demo. The API labels every response with its
provider and the UI shows a DEMO DATA badge, so these are never mistaken for
real prices. Output is deterministic per (product, region, day) and drifts a
little from day to day so history charts have something to show.

The prices are invented, but the stores are real retailers in each region and
every link opens that store's own search for the product, so clicking through
lands somewhere useful (with that store's real price, which will differ).
"""

import hashlib
import random
import urllib.parse
from datetime import date

from ..config import Region
from ..matching import Offer

# Real stores per region, with their product-search URL. {q} is the query
# (form-encoded), {path} the query as a URL path segment.
_AMAZON = "https://www.amazon.{tld}/s?k={{q}}"
_EBAY = "https://www.ebay.{tld}/sch/i.html?_nkw={{q}}"
STORES: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("Amazon", _AMAZON.format(tld="com")),
        ("Best Buy", "https://www.bestbuy.com/site/searchpage.jsp?st={q}"),
        ("Walmart", "https://www.walmart.com/search?q={q}"),
        ("Target", "https://www.target.com/s?searchTerm={q}"),
        ("Newegg", "https://www.newegg.com/p/pl?d={q}"),
        ("B&H Photo", "https://www.bhphotovideo.com/c/search?q={q}"),
    ],
    "CA": [
        ("Amazon.ca", _AMAZON.format(tld="ca")),
        ("Best Buy Canada", "https://www.bestbuy.ca/en-ca/search?search={q}"),
        ("Walmart Canada", "https://www.walmart.ca/search?q={q}"),
        ("eBay Canada", _EBAY.format(tld="ca")),
    ],
    "GB": [
        ("Amazon UK", _AMAZON.format(tld="co.uk")),
        ("Currys", "https://www.currys.co.uk/search?q={q}"),
        ("Argos", "https://www.argos.co.uk/search/{path}/"),
        ("John Lewis", "https://www.johnlewis.com/search?search-term={q}"),
        ("eBay UK", _EBAY.format(tld="co.uk")),
    ],
    "IE": [
        ("Amazon UK", _AMAZON.format(tld="co.uk")),
        ("Harvey Norman", "https://www.harveynorman.ie/catalogsearch/result/?q={q}"),
        ("eBay Ireland", _EBAY.format(tld="ie")),
    ],
    "NL": [
        ("Bol", "https://www.bol.com/nl/nl/s/?searchtext={q}"),
        ("Coolblue", "https://www.coolblue.nl/zoeken?query={q}"),
        ("MediaMarkt", "https://www.mediamarkt.nl/nl/search.html?query={q}"),
        ("Amazon.nl", _AMAZON.format(tld="nl")),
    ],
    "BE": [
        ("Bol", "https://www.bol.com/be/nl/s/?searchtext={q}"),
        ("Coolblue", "https://www.coolblue.be/nl/zoeken?query={q}"),
        ("MediaMarkt", "https://www.mediamarkt.be/nl/search.html?query={q}"),
        ("Amazon.com.be", _AMAZON.format(tld="com.be")),
    ],
    "DE": [
        ("Amazon.de", _AMAZON.format(tld="de")),
        ("MediaMarkt", "https://www.mediamarkt.de/de/search.html?query={q}"),
        ("Saturn", "https://www.saturn.de/de/search.html?query={q}"),
        ("eBay.de", _EBAY.format(tld="de")),
    ],
    "AT": [
        ("Amazon.de", _AMAZON.format(tld="de")),
        ("MediaMarkt", "https://www.mediamarkt.at/de/search.html?query={q}"),
        ("eBay.at", _EBAY.format(tld="at")),
    ],
    "CH": [
        ("Galaxus", "https://www.galaxus.ch/en/search?q={q}"),
        ("Digitec", "https://www.digitec.ch/en/search?q={q}"),
        ("Brack", "https://www.brack.ch/search?query={q}"),
    ],
    "FR": [
        ("Amazon.fr", _AMAZON.format(tld="fr")),
        ("Fnac", "https://www.fnac.com/SearchResult/ResultList.aspx?Search={q}"),
        ("Cdiscount", "https://www.cdiscount.com/search/10/{path}.html"),
        ("eBay.fr", _EBAY.format(tld="fr")),
    ],
    "ES": [
        ("Amazon.es", _AMAZON.format(tld="es")),
        ("MediaMarkt", "https://www.mediamarkt.es/es/search.html?query={q}"),
        ("eBay.es", _EBAY.format(tld="es")),
    ],
    "IT": [
        ("Amazon.it", _AMAZON.format(tld="it")),
        ("MediaWorld", "https://www.mediaworld.it/it/search.html?query={q}"),
        ("eBay.it", _EBAY.format(tld="it")),
    ],
    "SE": [
        ("Amazon.se", _AMAZON.format(tld="se")),
        ("Elgiganten", "https://www.elgiganten.se/search?q={q}"),
        ("Webhallen", "https://www.webhallen.com/se/search?searchString={q}"),
    ],
    "PL": [
        ("Amazon.pl", _AMAZON.format(tld="pl")),
        ("Allegro", "https://allegro.pl/listing?string={q}"),
        ("Media Expert", "https://www.mediaexpert.pl/search?query[menu_item]=&query[querystring]={q}"),
    ],
    "IN": [
        ("Amazon.in", _AMAZON.format(tld="in")),
        ("Flipkart", "https://www.flipkart.com/search?q={q}"),
        ("Croma", "https://www.croma.com/searchB?q={q}"),
    ],
    "JP": [
        ("Amazon.co.jp", _AMAZON.format(tld="co.jp")),
        ("Rakuten", "https://search.rakuten.co.jp/search/mall/{path}/"),
        ("Yodobashi", "https://www.yodobashi.com/?word={q}"),
    ],
    "SG": [
        ("Amazon.sg", _AMAZON.format(tld="sg")),
        ("Lazada", "https://www.lazada.sg/catalog/?q={q}"),
        ("Shopee", "https://shopee.sg/search?keyword={q}"),
    ],
    "AE": [
        ("Amazon.ae", _AMAZON.format(tld="ae")),
        ("Noon", "https://www.noon.com/uae-en/search/?q={q}"),
        ("Sharaf DG", "https://uae.sharafdg.com/?q={q}"),
    ],
    "AU": [
        ("Amazon.com.au", _AMAZON.format(tld="com.au")),
        ("JB Hi-Fi", "https://www.jbhifi.com.au/search?query={q}"),
        ("Harvey Norman", "https://www.harveynorman.com.au/catalogsearch/result/?q={q}"),
        ("eBay Australia", _EBAY.format(tld="com.au")),
    ],
}

# Rough price of a "typical" product in each currency, relative to USD.
_SCALE = {"USD": 1, "CAD": 1.35, "AUD": 1.5, "SGD": 1.35, "EUR": 0.92, "GBP": 0.8, "CHF": 0.9,
          "JPY": 150, "INR": 83, "AED": 3.67, "SEK": 10.5, "PLN": 4}
_SYMBOL = {"USD": "$", "CAD": "$", "AUD": "$", "SGD": "S$", "EUR": "€", "GBP": "£", "CHF": "CHF ",
           "JPY": "¥", "INR": "₹", "AED": "AED ", "SEK": "", "PLN": ""}
_SUFFIX = {"SEK": " kr", "PLN": " zł"}


def _format(value: float, currency: str) -> str:
    digits = 0 if currency in ("JPY", "INR") else 2
    return f"{_SYMBOL.get(currency, '')}{value:,.{digits}f}{_SUFFIX.get(currency, '')}"


def search_link(template: str, query: str) -> str:
    return template.format(q=urllib.parse.quote_plus(query), path=urllib.parse.quote(query, safe=""))


class DemoProvider:
    name = "demo"

    def __init__(self, today=date.today):
        self._today = today

    async def search(self, product: str, region: Region) -> list[Offer]:
        name = " ".join(product.split())
        if name.lower() in ("nothing", "no results"):
            return []

        seed = hashlib.sha256(f"{name.lower()}|{region.code}".encode()).hexdigest()
        base_rng = random.Random(seed)
        day_rng = random.Random(f"{seed}|{self._today().isoformat()}")

        currency = region.currency
        base = base_rng.uniform(80, 900) * _SCALE.get(currency, 1)
        stores = STORES.get(region.code) or STORES["US"]
        offers: list[Offer] = []

        def add(store: tuple[str, str], title: str, price: float, **extra) -> None:
            label, template = store
            price = round(price, 0 if currency in ("JPY", "INR") else 2)
            offers.append(Offer(label.upper(), title, price, _format(price, currency),
                                search_link(template, name), **extra))

        for i, store in enumerate(stores):
            drift = 1 + day_rng.uniform(-0.04, 0.04)
            price = base * (1 + i * 0.025 + base_rng.uniform(-0.02, 0.02)) * drift
            shipping = 0.0 if i % 2 == 0 else round(base * 0.012, 2)
            add(store, f"{name.title()} - {['Standard', 'Latest Model', 'Official'][i % 3]} Edition",
                price, shipping_cost=shipping, in_stock=i != 4)

        # Noise that a real results page contains and matching must reject.
        add(stores[0], f"Protective Case for {name.title()}", base * 0.04)
        add(stores[1 % len(stores)], f"{name.title()} Charger Cable 2m", base * 0.03)
        add(stores[2 % len(stores)], f"{name.title()} (Refurbished)", base * 0.7)
        return offers
