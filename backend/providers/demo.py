"""Made-up offers for developing the UI and running evals without the network.

Enabled only with PRICE_PROVIDER=demo. The API labels every response with its
provider and the UI shows a DEMO DATA badge, so these are never mistaken for
real prices. Output is deterministic per (product, region, day) and drifts a
little from day to day so history charts have something to show.
"""

import hashlib
import random
from datetime import date

from ..config import Region
from ..matching import Offer

_STORES = {
    "USD": ["Amazon", "Best Buy", "Walmart", "Target", "Newegg", "B&H Photo"],
    "GBP": ["Amazon UK", "Currys", "Argos", "John Lewis", "Very", "AO"],
    "EUR": ["Amazon", "MediaMarkt", "Coolblue", "Bol", "Fnac", "Saturn"],
}
_FALLBACK_STORES = ["Amazon", "Global Store", "TechHub", "Electro World", "Shop One", "Direct"]

# Rough price of a "typical" product in each currency, relative to USD.
_SCALE = {"USD": 1, "CAD": 1.35, "AUD": 1.5, "SGD": 1.35, "EUR": 0.92, "GBP": 0.8, "CHF": 0.9,
          "JPY": 150, "INR": 83, "AED": 3.67, "SEK": 10.5, "PLN": 4}
_SYMBOL = {"USD": "$", "CAD": "$", "AUD": "$", "SGD": "S$", "EUR": "€", "GBP": "£", "CHF": "CHF ",
           "JPY": "¥", "INR": "₹", "AED": "AED ", "SEK": "", "PLN": ""}
_SUFFIX = {"SEK": " kr", "PLN": " zł"}


def _format(value: float, currency: str) -> str:
    digits = 0 if currency in ("JPY", "INR") else 2
    return f"{_SYMBOL.get(currency, '')}{value:,.{digits}f}{_SUFFIX.get(currency, '')}"


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
        stores = _STORES.get(currency, _FALLBACK_STORES)
        offers: list[Offer] = []

        def add(store: str, title: str, price: float, **extra) -> None:
            price = round(price, 0 if currency in ("JPY", "INR") else 2)
            offers.append(Offer(store.upper(), title, price, _format(price, currency),
                                f"https://example.com/{store.lower().replace(' ', '-')}", **extra))

        for i, store in enumerate(stores):
            drift = 1 + day_rng.uniform(-0.04, 0.04)
            price = base * (1 + i * 0.025 + base_rng.uniform(-0.02, 0.02)) * drift
            shipping = 0.0 if i % 2 == 0 else round(base * 0.012, 2)
            add(store, f"{name.title()} - {['Standard', 'Latest Model', 'Official'][i % 3]} Edition",
                price, shipping_cost=shipping, in_stock=i != 4)

        # Noise that a real results page contains and matching must reject.
        add(stores[0], f"Protective Case for {name.title()}", base * 0.04)
        add(stores[1], f"{name.title()} Charger Cable 2m", base * 0.03)
        add(stores[2], f"{name.title()} (Refurbished)", base * 0.7)
        return offers
