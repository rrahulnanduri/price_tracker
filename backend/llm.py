"""Optional AI help, through ScrapeGraphAI. Off unless LLM_MODEL is set.

Two jobs, both narrow on purpose:

1. Extraction fallback. When the scraper loads a results page but its
   selectors find no offers (usually because Google changed its layout), the
   page is handed to an LLM to read instead. Every offer the LLM returns is
   checked against the page text and dropped if its price or title is not
   actually there, so an invented price can never reach the results.

2. Second opinion on matching. After the rules score each listing, the
   plausible ones are sent to the LLM in one batch with the question "is this
   exactly the product searched for?". It can drop a variant the rules let
   through ("Kids" trainers) or keep a real listing the rules missed. It never
   overrides a mismatched model number or an accessory the rules caught.

Neither job can break a search: any LLM failure is logged and the rules-only
result is used. Prices are always parsed by `backend.pricing`, never by the LLM.
"""

import asyncio
import html as html_lib
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from .config import Region, Settings
from .matching import Offer, apply_verdicts, fold, judge_candidates, tokenize
from .pricing import parse_number, parse_price
from .providers.base import parse_shipping, parse_stock

# ScrapeGraphAI sends usage telemetry unless told not to; search terms stay local.
os.environ.setdefault("SCRAPEGRAPHAI_TELEMETRY_ENABLED", "false")

logger = logging.getLogger(__name__)

MAX_PAGE_CHARS = 60_000      # page text sent for extraction; the results list fits comfortably
MAX_JUDGE_CANDIDATES = 30
TITLE_MATCH_SHARE = 0.6      # share of an extracted title's words that must appear on the page


class ExtractedOffer(BaseModel):
    store: str = Field(description="Merchant selling the item, e.g. 'Best Buy'")
    title: str = Field(description="Product title exactly as shown")
    price: str = Field(description="Price exactly as shown, including the currency symbol")
    url: str = Field(default="", description="Link to the offer, if shown")
    delivery: str = Field(default="", description="Delivery or shipping text, if shown")
    availability: str = Field(default="", description="Stock text such as 'In stock', if shown")


class ExtractedOffers(BaseModel):
    offers: list[ExtractedOffer] = Field(default_factory=list)


class Verdict(BaseModel):
    index: int
    same_product: bool
    reason: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


# (prompt, source text, output schema) -> parsed answer. Swappable so tests need no LLM.
Runner = Callable[[str, str, type[BaseModel]], dict]


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class LLMOptions:
    fallback: bool = True
    judge: bool = True


def graph_config(settings: Settings) -> dict:
    """ScrapeGraphAI configuration from settings (model is "provider/name", e.g. "openai/gpt-4o-mini")."""
    llm: dict = {"model": settings.llm_model, "temperature": 0}
    if settings.llm_api_key:
        llm["api_key"] = settings.llm_api_key
    if settings.llm_base_url:
        llm["base_url"] = settings.llm_base_url
    if settings.llm_model_tokens:
        llm["model_tokens"] = settings.llm_model_tokens
    return {"llm": llm, "verbose": False, "headless": True}


def scrapegraph_runner(config: dict) -> Runner:
    def run(prompt: str, source: str, schema: type[BaseModel]) -> dict:
        try:
            from scrapegraphai.graphs import SmartScraperGraph
        except ImportError as exc:
            raise LLMError("ScrapeGraphAI is not installed. Run: pip install -r requirements-llm.txt") from exc
        # A source that does not start with "http" is treated as page content, not a URL.
        graph = SmartScraperGraph(prompt=prompt, source=source, config=config, schema=schema)
        answer = graph.run()
        if not isinstance(answer, dict):
            raise LLMError(f"Unexpected LLM answer: {type(answer).__name__}")
        return answer

    return run


def _parse(answer: dict, schema: type[BaseModel]) -> BaseModel:
    # ScrapeGraphAI sometimes wraps the structured answer in {"content": ...}.
    if set(answer) == {"content"} and isinstance(answer["content"], dict):
        answer = answer["content"]
    try:
        return schema.model_validate(answer)
    except ValidationError as exc:
        raise LLMError(f"LLM answer did not match the expected shape: {exc.error_count()} errors") from exc


def page_text(html: str) -> str:
    """Readable text of a page, with links kept, trimmed to what an LLM needs."""
    try:
        from scrapegraphai.utils.convert_to_md import convert_to_md

        text = convert_to_md(html)
    except Exception:  # missing dependency or unparseable HTML: fall back to simple stripping
        text = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        # Keep links as "[text](href)" so offers can still be linked.
        text = re.sub(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.S | re.I)
        text = re.sub(r"<(?:br|/p|/div|/tr|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
    return re.sub(r"[ \t]+", " ", text)[:MAX_PAGE_CHARS]


def _appears_in(page: str, title: str) -> bool:
    words = set(tokenize(title))
    if not words:
        return False
    page_words = set(tokenize(page))
    return len(words & page_words) / len(words) >= TITLE_MATCH_SHARE


# Digits with thousands/decimal separators, including non-breaking spaces but not newlines.
_NUMBER_ON_PAGE = re.compile(r"\d(?:[\d.,']|[^\S\n])*\d|\d")


def _prices_on_page(page: str) -> set[float]:
    """Every number on the page, parsed the same way prices are, for checking LLM output."""
    values = set()
    for match in _NUMBER_ON_PAGE.finditer(page):
        value = parse_number(match.group(0))
        if value is not None:
            values.add(round(value, 2))
    return values


def _absolute(url: str) -> str:
    from .providers.google_shopping import resolve_link

    url = resolve_link(url.strip()) if url else ""
    return url if url.startswith(("http://", "https://")) else ""


class LLMHelper:
    def __init__(self, runner: Runner, options: LLMOptions | None = None, model: str = ""):
        self.runner = runner
        self.options = options or LLMOptions()
        self.model = model

    async def _ask(self, prompt: str, source: str, schema: type[BaseModel]) -> BaseModel:
        answer = await asyncio.to_thread(self.runner, prompt, source, schema)
        return _parse(answer, schema)

    # -- extraction fallback -------------------------------------------------

    async def extract_offers(self, page: str, product: str, region: Region) -> list[Offer]:
        """Offers read from page text by the LLM, keeping only ones verifiably on the page."""
        prompt = (
            f'This is a shopping results page for "{product}". List every product offer on it. '
            "For each, give the store, the product title, the price exactly as written (with its "
            "currency symbol), the link, and any delivery and stock text. Copy text verbatim; "
            "do not guess or convert anything. Skip ads for unrelated products."
        )
        try:
            parsed = await self._ask(prompt, page, ExtractedOffers)
        except Exception as exc:
            logger.warning("LLM extraction failed for %r: %s", product, exc)
            return []

        flat_page = fold(page)
        page_prices = _prices_on_page(page)
        offers: list[Offer] = []
        dropped = 0
        for item in parsed.offers:
            price = parse_price(item.price, region.currency)
            # The price must be in the region's currency and appear as a number on the page;
            # the title must be mostly made of words that are on the page.
            if (
                price is None
                or price.currency != region.currency
                or price.value not in page_prices
                or not item.store.strip()
                or not _appears_in(flat_page, item.title)
            ):
                dropped += 1
                continue
            extras = f"{item.delivery} | {item.availability}"
            offers.append(Offer(
                store=item.store.strip().upper(),
                title=item.title.strip()[:120],
                price=price.value,
                price_text=item.price.strip(),
                url=_absolute(item.url),
                shipping_cost=parse_shipping(extras, region.currency),
                in_stock=parse_stock(extras),
                extracted_by="ai",
            ))
        if dropped:
            logger.info("LLM extraction: dropped %d offer(s) not found on the page", dropped)
        return offers

    # -- second opinion on matching ------------------------------------------

    async def review_matches(self, query: str, offers: list[Offer], min_relevance: float) -> int:
        """Ask whether each plausible listing is the searched product; apply answers in place.

        Returns how many listings changed from kept to rejected or back. Offers must be scored.
        """
        candidates = judge_candidates(offers)[:MAX_JUDGE_CANDIDATES]
        if not candidates:
            return 0
        listing = "\n".join(f"{i}. {o.title} (sold by {o.store})" for i, o in enumerate(candidates))
        prompt = (
            f'A shopper searched for "{query}". For each numbered listing below, decide whether it is '
            "exactly that product: the same model and variant (not a Pro/Mini/Kids/other-size version, "
            "not a different generation or capacity than asked for), and the item being sold rather than "
            "an accessory, part, add-on, or a bundle led by a different product. Colour and harmless extras "
            "in a bundle do not matter. Answer for every index."
        )
        try:
            parsed = await self._ask(prompt, listing, Verdicts)
        except Exception as exc:
            logger.warning("LLM match review failed for %r: %s", query, exc)
            return 0
        verdicts = {v.index: v.same_product for v in parsed.verdicts}
        return apply_verdicts(candidates, verdicts, min_relevance)


def build_llm_helper(settings: Settings) -> LLMHelper | None:
    if not settings.llm_model:
        return None
    options = LLMOptions(fallback=settings.llm_fallback, judge=settings.llm_judge)
    if not (options.fallback or options.judge):
        return None
    return LLMHelper(scrapegraph_runner(graph_config(settings)), options, settings.llm_model)
