from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scrapling.fetchers import StealthyFetcher
import re
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REGION_CONFIG = {
    "US": {"gl": "us", "hl": "en", "currency": "USD", "label": "United States"},
    "GB": {"gl": "gb", "hl": "en", "currency": "GBP", "label": "United Kingdom"},
    "IN": {"gl": "in", "hl": "en", "currency": "INR", "label": "India"},
    "DE": {"gl": "de", "hl": "de", "currency": "EUR", "label": "Germany"},
    "FR": {"gl": "fr", "hl": "fr", "currency": "EUR", "label": "France"},
    "AU": {"gl": "au", "hl": "en", "currency": "AUD", "label": "Australia"},
    "CA": {"gl": "ca", "hl": "en", "currency": "CAD", "label": "Canada"},
    "JP": {"gl": "jp", "hl": "ja", "currency": "JPY", "label": "Japan"},
    "SG": {"gl": "sg", "hl": "en", "currency": "SGD", "label": "Singapore"},
    "AE": {"gl": "ae", "hl": "en", "currency": "AED", "label": "UAE"},
}


class SearchRequest(BaseModel):
    product: str
    country: str = "US"


def parse_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind('.') > cleaned.rfind(','):
            cleaned = cleaned.replace(',', '')
        else:
            cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        val = float(cleaned)
        return val if 1 <= val <= 100_000 else None
    except ValueError:
        return None


async def scrape_google_shopping(product: str, gl: str, hl: str) -> list[dict]:
    query = urllib.parse.quote_plus(product)
    url = f"https://www.google.com/search?q={query}&tbm=shop&gl={gl}&hl={hl}&num=20"

    page = await StealthyFetcher().async_fetch(url)

    # Scrapling: find all price elements by regex — no fragile CSS class names
    price_elements = page.find_by_regex(
        r'[$€£¥₹]\s*\d[\d,. ]*|\d[\d,.]*\s*[$€£¥₹]',
        first_match=False
    )

    results = []
    seen_stores = set()

    for price_el in price_elements:
        price_text = price_el.text.strip()
        price = parse_price(price_text)
        if not price:
            continue

        # find_ancestor takes a callable — check for 'mnr-c' in class attribute
        card = price_el.find_ancestor(
            lambda el: 'mnr-c' in (el.attrib.get('class') or '')
        )
        if not card:
            continue

        # Store — css selector still works for known stable classes
        store_els = card.css("div.UsGWMe")
        store = store_els[0].text.strip() if store_els else None

        if not store:
            # Fallback: short text divs with no digits
            for d in card.find_all("div"):
                t = (d.text or "").strip()
                if 3 < len(t) < 35 and not re.search(r'\d', t) and d.attrib.get("class"):
                    store = t
                    break

        if not store or store.upper() in seen_stores:
            continue

        # Title — find first meaningful text element in card
        title = product
        for tag in ("h3", "h4", "div", "span"):
            for el in card.find_all(tag):
                t = (el.text or "").strip()
                if len(t) > 15 and not re.search(r'^[$€£¥₹\d(]', t) and t != store:
                    title = t
                    break
            if title != product:
                break

        # Link — find first anchor in card
        link_el = card.find("a")
        href = link_el.attrib.get("href", "") if link_el else ""
        if href.startswith("/url?"):
            m = re.search(r'[?&]url=([^&]+)', href)
            href = urllib.parse.unquote(m.group(1)) if m else "https://www.google.com" + href
        elif href.startswith("/"):
            href = "https://www.google.com" + href

        seen_stores.add(store.upper())
        results.append({
            "store": store.upper(),
            "title": title[:80],
            "price": price,
            "price_text": price_text,
            "url": href,
        })

        if len(results) == 7:
            break

    return sorted(results, key=lambda x: x["price"])


@app.post("/api/search")
async def search_prices(req: SearchRequest):
    country = req.country.upper()
    config = REGION_CONFIG.get(country, REGION_CONFIG["US"])

    try:
        results = await scrape_google_shopping(req.product, config["gl"], config["hl"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not results:
        raise HTTPException(status_code=404, detail="No results found. Try a different product name.")

    return {
        "product": req.product,
        "region": config["label"],
        "currency": config["currency"],
        "results": results,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
