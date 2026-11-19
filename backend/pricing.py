"""Turning price display text ("1.299,00 €", "AED 499", "S$1,299") into a number and a currency."""

import re
from dataclasses import dataclass

# Unambiguous markers, longest first so "US$" wins over "$" and "A$" over "$".
_CURRENCY_MARKERS: list[tuple[str, str]] = [
    ("US$", "USD"), ("USD", "USD"),
    ("CA$", "CAD"), ("C$", "CAD"), ("CAD", "CAD"),
    ("AU$", "AUD"), ("A$", "AUD"), ("AUD", "AUD"),
    ("SG$", "SGD"), ("S$", "SGD"), ("SGD", "SGD"),
    ("EUR", "EUR"), ("€", "EUR"),
    ("GBP", "GBP"), ("£", "GBP"),
    ("JPY", "JPY"), ("JP¥", "JPY"), ("¥", "JPY"), ("円", "JPY"),
    ("INR", "INR"), ("₹", "INR"), ("Rs.", "INR"), ("Rs", "INR"),
    ("AED", "AED"), ("Dhs", "AED"), ("د.إ", "AED"),
    ("CHF", "CHF"), ("Fr.", "CHF"),
    ("SEK", "SEK"), ("PLN", "PLN"), ("zł", "PLN"),
]

# Markers whose meaning depends on where you are shopping.
_DOLLAR_CURRENCIES = {"USD", "CAD", "AUD", "SGD"}
_KRONA_CURRENCIES = {"SEK"}

# Plausible price range per currency; outside it the text is treated as noise.
_DEFAULT_BOUNDS = (0.5, 100_000)
_BOUNDS = {
    "JPY": (50, 15_000_000),
    "INR": (10, 10_000_000),
    "SEK": (5, 1_000_000),
    "PLN": (2, 500_000),
    "AED": (2, 400_000),
}

# Spaces and apostrophes only count as thousands separators ("1 299,00", "1'299.00"),
# so "$449 2 offers" is not read as 4492.
_NBSP = chr(0xA0) + chr(0x202F)  # non-breaking and narrow no-break space
_NUMBER = (
    rf"\d{{1,3}}(?:[{_NBSP} '](?=\d{{3}})\d{{3}})+(?:[.,]\d{{1,2}})?"
    r"|\d[\d.,]*\d|\d"
)
_MARKER = "|".join(re.escape(m) for m, _ in _CURRENCY_MARKERS) + r"|\$|kr"

# A price as it appears in page text: marker before or after the number. The
# letter guards stop "controllers 5" matching the "Rs" marker.
PRICE_PATTERN = (
    rf"(?<![A-Za-z])(?:{_MARKER})\s*(?:{_NUMBER})"
    rf"|(?:{_NUMBER})\s*(?:{_MARKER})(?![A-Za-z])"
)
_PRICE_RE = re.compile(PRICE_PATTERN, re.IGNORECASE)
_NUMBER_RE = re.compile(_NUMBER)


@dataclass(frozen=True)
class Price:
    value: float
    currency: str


def detect_currency(text: str, default_currency: str) -> str | None:
    """Currency named in the text, resolving "$" and "kr" by the shopper's region."""
    lowered = text.lower()
    for marker, currency in _CURRENCY_MARKERS:
        if marker.lower() in lowered:
            return currency
    if "$" in text:
        return default_currency if default_currency in _DOLLAR_CURRENCIES else "USD"
    if re.search(r"\bkr\b", lowered):
        return default_currency if default_currency in _KRONA_CURRENCIES else "SEK"
    return None


def _normalise_separators(number: str) -> str:
    """Turn a locale-formatted number ("1.299,00", "1,299.00", "1 299") into float syntax."""
    number = re.sub(r"[\s']", "", number)
    has_comma, has_dot = "," in number, "." in number

    if has_comma and has_dot:
        # Whichever separator comes last is the decimal point.
        if number.rfind(".") > number.rfind(","):
            return number.replace(",", "")
        return number.replace(".", "").replace(",", ".")

    if has_comma or has_dot:
        sep = "," if has_comma else "."
        parts = number.split(sep)
        # One separator followed by 1-2 digits is a decimal ("12,99");
        # otherwise it groups thousands ("1.299", "1,50,000").
        if len(parts) == 2 and len(parts[1]) <= 2:
            return number.replace(sep, ".")
        return number.replace(sep, "")

    return number


def parse_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text or "")
    if not match:
        return None
    try:
        return float(_normalise_separators(match.group(0).strip(".,")))
    except ValueError:
        return None


def parse_price(text: str | None, default_currency: str = "USD") -> Price | None:
    """Extract the first price from display text, or None if it isn't a plausible price.

    Text with no currency marker at all is assumed to be in `default_currency`.
    """
    if not text:
        return None
    priced = _PRICE_RE.search(text)
    snippet = priced.group(0) if priced else text
    value = parse_number(snippet)
    if value is None:
        return None
    currency = detect_currency(snippet, default_currency) or default_currency
    low, high = _BOUNDS.get(currency, _DEFAULT_BOUNDS)
    if not low <= value <= high:
        return None
    return Price(round(value, 2), currency)


def find_marked_price(text: str | None, default_currency: str = "USD") -> Price | None:
    """Like parse_price, but only for text that carries a currency marker ("$4.99", not "14")."""
    priced = _PRICE_RE.search(text or "")
    return parse_price(priced.group(0), default_currency) if priced else None
