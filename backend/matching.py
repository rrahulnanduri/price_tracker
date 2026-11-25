"""Deciding which offers are actually the product that was searched for.

A shopping results page mixes the product with accessories for it, other
models in the same line, games and add-ons that mention it, and used units.
Ranking those by price puts a phone case above the phone, so every offer gets
a relevance score first and only offers above the threshold are ranked.

The rules here are measured by `python -m evals.run`; change them against
that, not by feel.
"""

import re
import statistics
import unicodedata
import urllib.parse
from dataclasses import dataclass, field

STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "of", "in", "to", "by", "new", "buy",
    "de", "het", "een", "en", "met", "voor", "der", "die", "das", "und", "mit", "fur",
    "le", "la", "les", "et", "avec", "pour", "el", "los", "con", "para", "il", "per",
    "inch", "inches", "series", "edition", "gen", "generation", "model", "version",
}

# Words that mean "this is something for the product, not the product".
ACCESSORY_TERMS = {
    "case", "cases", "cover", "covers", "sleeve", "skin", "skins", "protector", "protectors",
    "charger", "chargers", "cable", "cables", "adapter", "adaptor", "dock", "stand", "mount",
    "holder", "strap", "straps", "band", "bands", "bumper", "faceplate", "faceplates", "decal",
    "sticker", "stickers", "replacement", "spare", "refill", "pouch", "bag", "lid",
    "controller", "controllers", "gamepad", "headset", "stylus", "pencil", "keyboard",
    "battery", "batteries", "remote", "filter", "filters", "cartridge", "cartridges",
    "eartips", "tips", "cushions", "earpads", "screenprotector", "attachment", "attachments",
    "refills", "liners", "heads",
    # nl / de / fr / es / it / sv
    "hoes", "hoesje", "beschermhoes", "oplader", "kabel", "hulle", "schutzhulle", "panzerglas",
    "displayschutz", "ladegerat", "tasche", "coque", "etui", "housse", "chargeur", "vitrine",
    "funda", "cargador", "custodia", "skal", "laddare", "hylla", "opzetborstel", "opzetborstels",
    "aufsteckbursten", "armband", "schutzfolie", "capsule", "capsules",
}
ACCESSORY_PHRASES = (
    "tempered glass", "screen protector", "ear tips", "charging station", "carrying case",
    "replacement part", "wall mount", "lighting kit", "kit d eclairage",
)
# "Case" here is a part of the product itself, not an accessory.
BENIGN_PHRASES = re.compile(
    r"\b(?:alumin(?:i)?um|titanium|stainless steel|steel|ceramic|charging|magsafe charging) case\b"
)
# Accessory and condition words in scripts the tokenizer does not cover.
CJK_ACCESSORY = ("ケース", "カバー", "フィルム", "イヤーパッド", "交換用", "保護", "充電器", "ストラップ")
CJK_INCLUDED = "付き"   # "comes with": the accessory is an extra, not the item
CJK_USED = ("中古", "整備済")
# Hindi: case, cover, charger, and "for use with" (Amazon.in's wording for accessories).
INDIC_ACCESSORY = ("केस", "कवर", "चार्जर", "के साथ इस्तेमाल")

# "<accessory> for <product>" phrasings, in the languages of the supported regions.
COMPATIBILITY_MARKERS = (
    "for", "compatible with", "fits", "designed for", "voor", "geschikt voor",
    "fur", "passend fur", "kompatibel mit", "pour", "compatible avec", "para",
    "compatible con", "per", "compatibile con", "till",
)
# What follows these is an extra in a bundle, not the thing being sold.
_BUNDLE_JOINERS = re.compile(
    r"\b(?:with|incl|including|inclusief|inkl|inklusive|avec|con|mit|met|med)\b|\+|&"
)

CONDITION_TERMS = {
    "refurbished": "refurbished", "generaluberholt": "refurbished",
    "reconditionne": "refurbished", "reacondicionado": "refurbished",
    "ricondizionato": "refurbished",
    "used": "used", "pre owned": "used", "preowned": "used", "second hand": "used",
    "tweedehands": "used", "gebraucht": "used", "occasion": "used", "open box": "used",
    "begagnad": "used", "usato": "used", "usado": "used",
    "erneuert": "refurbished", "gebruikt": "used",
    # "as good as new" / "in good condition": how second-hand listings describe themselves
    "like new": "used", "als nieuw": "used", "nette staat": "used", "goede staat": "used",
    "wie neu": "used", "neuwertig": "used", "comme neuf": "used", "como nuevo": "used",
    "come nuovo": "used", "seminuevo": "used",
}

# Common shorthand, expanded so "ps5" and "PlayStation 5" compare equal.
ALIASES = {
    "ps5": "playstation 5", "ps4": "playstation 4", "xsx": "xbox series x",
    "mbp": "macbook pro", "mba": "macbook air",
    "renewed": "refurbished", "reconditioned": "refurbished", "refurb": "refurbished",
    "qt": "quart", "aluminum": "aluminium",
}

# Words that distinguish models in a product line. One of these in the title
# but not the query (or the reverse) means a different product.
STRONG_VARIANTS = {"pro", "max", "plus", "mini", "ultra", "lite", "se", "fe", "xl"}
# Softer variant words: only a mismatch when the shopper asked for them.
QUERY_VARIANTS = STRONG_VARIANTS | {"air", "slim", "digital", "oled", "s", "x", "xs"}

# Bundles: the item plus games, kits, vouchers or cover plans. Someone asking for "playstation 5 console"
# wants the console, so these are dropped unless the query asks for them.
BUNDLE_TERMS = {"bundle", "bundel", "combo", "voucher", "accessories", "accessory", "zubehor", "accessoires",
                "applecare"}
# Extras that make a bundle when they follow "with" / "w/" / "+" ("Console with Extra Controller").
BUNDLE_EXTRAS = {"controller", "controllers", "dualsense", "game", "games", "spiel", "spiele", "jeu", "jeux",
                 "headset"}
_BUNDLE_SPLIT = re.compile(r"\b(?:with|w|incl|including|inclusief|inkl|inklusive|avec|con|mit|met|med)\b")

OUTLIER_FRACTION = 0.3   # an offer under 30% of the median price is not the same product
OUTLIER_MIN_OFFERS = 3   # ...but only trust the median with this many offers
KEY_TERM_MIN_OFFERS = 4  # need this many results before "most results say X" means anything
DEFAULT_MIN_RELEVANCE = 0.7


def safe_url(url: str) -> str:
    """The URL if it is an absolute http(s) link, else "". Offer links come from scraped pages,
    so anything else (javascript:, data:, protocol-relative) must never reach a link or webhook."""
    url = (url or "").strip()
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    return url if parts.scheme.lower() in ("http", "https") and parts.netloc else ""


@dataclass
class Offer:
    store: str
    title: str
    price: float
    price_text: str
    url: str = ""
    shipping_cost: float | None = None   # None = unknown, 0 = free
    in_stock: bool | None = None         # None = unknown
    condition: str = "new"
    relevance: float = 0.0
    flags: list[str] = field(default_factory=list)
    extracted_by: str = "rules"          # "rules" or "ai" (the LLM extraction fallback)
    source: str = ""                     # which price source found it, e.g. "google", "kieskeurig"

    def __post_init__(self) -> None:
        self.url = safe_url(self.url)

    @property
    def total(self) -> float:
        return round(self.price + (self.shipping_cost or 0), 2)

    def to_dict(self) -> dict:
        return {
            "store": self.store,
            "title": self.title,
            "price": self.price,
            "price_text": self.price_text,
            "url": self.url,
            "shipping_cost": self.shipping_cost,
            "total": self.total,
            "in_stock": self.in_stock,
            "condition": self.condition,
            "relevance": round(self.relevance, 2),
            "extracted_by": self.extracted_by,
            "source": self.source,
            "ai_checked": any(f in self.flags for f in ("ai_confirmed", "ai_rejected", "ai_agreed")),
        }


_DOMAIN_SUFFIX = re.compile(
    r"\.(?:com|net|org|nl|be|de|at|ch|fr|es|it|se|pl|ie|in|jp|sg|ae|ca|au|uk"
    r"|co\.uk|co\.jp|com\.au|com\.be)$"
)


def store_key(store: str) -> str:
    """One key per shop across sources: "Nedgame.nl", "NEDGAME" and "www.nedgame.nl" match."""
    key = fold(store).strip()
    key = re.sub(r"^(?:https?://)?(?:www\.)?", "", key)
    key = _DOMAIN_SUFFIX.sub("", key)
    return re.sub(r"[^a-z0-9]", "", key)


def fold(text: str) -> str:
    """Lowercase and strip accents so "Hülle" matches "hulle"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    folded = _expand_aliases(fold(text))
    # Split "256gb" into "256 gb" so model codes match however they are written.
    folded = re.sub(r"(\d)([a-z])", r"\1 \2", folded)
    folded = re.sub(r"([a-z])(\d)", r"\1 \2", folded)
    # Again after splitting, so "6qt" -> "6 qt" -> "6 quart".
    return re.findall(r"[a-z0-9]+", _expand_aliases(folded))


def _expand_aliases(text: str) -> str:
    for short, full in ALIASES.items():
        text = re.sub(rf"\b{short}\b", full, text)
    return text


def _content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS]


def _model_codes(query: str) -> list[list[str]]:
    """Token runs for each model number in the query: "c4" -> ["c", "4"], "15" -> ["15"]."""
    codes = []
    for word in fold(query).split():
        if re.search(r"\d", word):
            code = [t for t in tokenize(word) if t not in STOPWORDS]
            if code:
                codes.append(code)
    return codes


def _contains_run(tokens: list[str], run: list[str]) -> bool:
    """True if `run` appears as consecutive tokens, so "C3 ... 4K" does not pass for "C4"."""
    return any(tokens[i:i + len(run)] == run for i in range(len(tokens) - len(run) + 1))


def _mostly_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return not letters or sum(ch.isascii() for ch in letters) / len(letters) >= 0.7


def detect_condition(title: str) -> str:
    if any(term in title for term in CJK_USED):
        return "used"
    text = " ".join(tokenize(title))
    for term, condition in CONDITION_TERMS.items():
        if re.search(rf"\b{term}\b", text):
            return condition
    return "new"


def _is_accessory_for(title_text: str, query_tokens: list[str]) -> bool:
    """True for "<something> for <the product>" titles."""
    if not query_tokens:
        return False
    first = re.search(rf"\b{re.escape(query_tokens[0])}\b", title_text)
    if not first:
        return False
    # Only a "for" before the first mention of the product counts: "Landegestell für DJI Mini 4 Pro"
    # is an accessory, "Apple iPhone 15 ... for AT&T" is the phone.
    before = title_text[:first.start()]
    return any(
        re.search(rf"\b{re.escape(marker)} (?:\w+ ){{0,5}}$", before)
        for marker in COMPATIBILITY_MARKERS
    )


def _is_accessory(title: str, title_text: str, q_tokens: list[str], q_set: set[str]) -> bool:
    if any(term in title for term in CJK_ACCESSORY) and CJK_INCLUDED not in title:
        return True
    if any(term in title for term in INDIC_ACCESSORY):
        return True
    # Someone searching for "iphone 15 case" wants the "case for iPhone 15" titles.
    shopping_for_accessory = bool(q_set & ACCESSORY_TERMS)
    if not shopping_for_accessory and _is_accessory_for(title_text, q_tokens):
        return True
    # Only the part before a bundle joiner names the thing being sold.
    lead = _BUNDLE_JOINERS.split(BENIGN_PHRASES.sub(" ", title_text))[0]
    lead_tokens = set(lead.split())
    if (lead_tokens & ACCESSORY_TERMS) - q_set:
        return True
    query_text = " ".join(q_tokens)
    return any(phrase in lead and phrase not in query_text for phrase in ACCESSORY_PHRASES)


def _is_bundle(title_tokens: list[str], title_text: str, query_words: set[str]) -> bool:
    """The item sold together with extras the shopper did not ask for."""
    if (set(title_tokens) & BUNDLE_TERMS) - query_words:
        return True
    parts = _BUNDLE_SPLIT.split(title_text, maxsplit=1)
    extras = set(parts[1].split()) if len(parts) == 2 else set()
    return bool((extras & BUNDLE_EXTRAS) - query_words)


def score_relevance(query: str, title: str, store: str = "",
                    key_terms: frozenset[str] = frozenset()) -> tuple[float, list[str]]:
    """Score 0..1 for how likely `title` is the product named by `query`, with reasons.

    `key_terms` are query words that most of the other results contain (see
    `rank_offers`); an offer missing one is the odd one out.
    """
    q_tokens = _content_tokens(query)
    t_tokens = _content_tokens(title)
    if not q_tokens or not t_tokens:
        return 0.0, ["empty"]

    q_set, t_set = set(q_tokens), set(t_tokens)
    title_tokens = tokenize(title)
    title_text = " ".join(title_tokens)
    # A brand often appears only as the store ("BILLY bookcase" sold by IKEA).
    searchable = t_set | set(tokenize(store))
    flags: list[str] = []

    score = sum(1 for t in q_tokens if t in searchable) / len(q_tokens)

    # A missing model number is a different model: "iphone 15" is not "iphone 14",
    # and "WH-1000XM5" is not "WF-1000XM5".
    if any(not _contains_run(title_tokens, code) for code in _model_codes(query)):
        score *= 0.3
        flags.append("wrong_model")

    if (t_set & STRONG_VARIANTS) - q_set or (q_set & QUERY_VARIANTS) - t_set:
        score *= 0.5
        flags.append("variant_mismatch")

    # "MX Anywhere 3S" among results for "MX Master 3S": it lacks a word nearly
    # every other result has. Skipped for titles in scripts the tokenizer can't read.
    if (key_terms - searchable) and _mostly_latin(title):
        score *= 0.6
        flags.append("missing_key_term")

    # The product named only at the end ("Spider-Man 2 - PS5"), or only after a
    # bundle joiner ("Keyboard combo with MX Master 3S"), is not what is being sold.
    positions = [i for i, t in enumerate(t_tokens) if t in q_set]
    lead = set(_BUNDLE_JOINERS.split(title_text)[0].split())
    if positions and positions[0] >= 3 and positions[0] / len(t_tokens) >= 0.5:
        score *= 0.5
        flags.append("late_mention")
    elif len(lead & q_set) / len(q_set) < 0.5 and _mostly_latin(title):
        score *= 0.5
        flags.append("bundle_extra")

    if _is_bundle(title_tokens, title_text, set(tokenize(query))):
        score *= 0.6
        flags.append("bundle")

    if _is_accessory(title, title_text, tokenize(query), q_set):
        score *= 0.25
        flags.append("accessory")

    return round(min(score, 1.0), 3), flags


def _key_terms(query: str, offers: list["Offer"]) -> frozenset[str]:
    """Query words that at least half of the offers contain."""
    if len(offers) < KEY_TERM_MIN_OFFERS:
        return frozenset()
    q_set = set(_content_tokens(query))
    token_sets = [set(_content_tokens(o.title)) | set(tokenize(o.store)) for o in offers]
    return frozenset(
        t for t in q_set if sum(t in tokens for tokens in token_sets) / len(offers) >= 0.5
    )


def score_offers(query: str, offers: list[Offer]) -> None:
    """Set relevance, flags and condition on every offer (in place)."""
    key_terms = _key_terms(query, offers)
    for offer in offers:
        offer.relevance, offer.flags = score_relevance(query, offer.title, offer.store, key_terms)
        offer.condition = detect_condition(offer.title)


def select_offers(
    query: str,
    offers: list[Offer],
    *,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    limit: int = 8,
) -> tuple[list[Offer], list[Offer]]:
    """Return (ranked, rejected) from already-scored offers: one per store, cheapest total first."""
    wants_condition = detect_condition(query)
    kept: list[Offer] = []
    rejected: list[Offer] = []

    for offer in offers:
        if offer.relevance < min_relevance:
            rejected.append(offer)
        elif (offer.condition == "new") != (wants_condition == "new"):
            # Used units when shopping new, or new units when shopping refurbished.
            offer.flags.append("condition")
            rejected.append(offer)
        else:
            kept.append(offer)

    # A price far below the rest is almost always a mislabelled accessory or a
    # per-month instalment price, not a bargain.
    if len(kept) >= OUTLIER_MIN_OFFERS:
        median = statistics.median(o.price for o in kept)
        for offer in list(kept):
            if offer.price < median * OUTLIER_FRACTION:
                offer.flags.append("price_outlier")
                kept.remove(offer)
                rejected.append(offer)

    # One offer per store: in stock before out of stock, then cheapest total.
    best: dict[str, Offer] = {}
    for offer in kept:
        key = store_key(offer.store)
        if key not in best or _sort_key(offer) < _sort_key(best[key]):
            best[key] = offer

    return sorted(best.values(), key=_sort_key)[:limit], rejected


def rank_offers(
    query: str,
    offers: list[Offer],
    *,
    min_relevance: float = DEFAULT_MIN_RELEVANCE,
    limit: int = 8,
) -> tuple[list[Offer], list[Offer]]:
    """Score then select, with the rules alone (no AI second opinion)."""
    score_offers(query, offers)
    return select_offers(query, offers, min_relevance=min_relevance, limit=limit)


# Offers the rules flagged for these reasons are left alone by the AI second
# opinion: a mismatched model number or an accessory is a confident call.
HARD_FLAGS = {"wrong_model", "accessory", "empty"}
JUDGE_FLOOR = 0.35   # below this the rules are confident it is a different product


def judge_candidates(offers: list[Offer]) -> list[Offer]:
    """Offers worth a second opinion: plausible matches the rules were not certain about."""
    return [o for o in offers if o.relevance >= JUDGE_FLOOR and not (set(o.flags) & HARD_FLAGS)]


def apply_verdicts(candidates: list[Offer], verdicts: dict[int, bool], min_relevance: float) -> int:
    """Apply same-product verdicts (keyed by candidate index). Returns how many changed an outcome."""
    changed = 0
    for index, same in verdicts.items():
        if not 0 <= index < len(candidates):
            continue
        offer = candidates[index]
        kept_before = offer.relevance >= min_relevance
        if same and not kept_before:
            offer.relevance = min_relevance
            offer.flags.append("ai_confirmed")
        elif not same and kept_before:
            offer.relevance = 0.0
            offer.flags.append("ai_rejected")
        else:
            offer.flags.append("ai_agreed")
        changed += kept_before != (offer.relevance >= min_relevance)
    return changed


def _sort_key(offer: Offer) -> tuple:
    return (offer.in_stock is False, offer.total, -offer.relevance)
