"""The optional AI layer, tested with a scripted stand-in for the LLM (no network, no model)."""

import asyncio
import dataclasses
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import REGIONS, load_settings
from backend.llm import ExtractedOffers, LLMHelper, LLMOptions, Verdicts, build_llm_helper, graph_config, page_text
from backend.matching import Offer, rank_offers, score_offers, select_offers
from backend.providers.google_shopping import GoogleShoppingProvider
from evals import run as evals

from .conftest import offer

US, NL = REGIONS["US"], REGIONS["NL"]
PAGES = Path(__file__).parent.parent / "evals" / "pages"


class ScriptedLLM:
    """Answers each prompt with the next scripted reply, recording what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, str, type]] = []

    def __call__(self, prompt, source, schema):
        self.calls.append((prompt, source, schema))
        reply = self.replies.pop(0) if self.replies else {}
        if isinstance(reply, Exception):
            raise reply
        return reply(prompt, source, schema) if callable(reply) else reply


def helper(*replies, **options) -> tuple[LLMHelper, ScriptedLLM]:
    llm = ScriptedLLM(*replies)
    return LLMHelper(llm, LLMOptions(**options), model="test/model"), llm


NEW_LAYOUT_ANSWER = {"offers": [
    {"store": "Bol", "title": "Nintendo Switch OLED Console - Wit", "price": "€ 319,00",
     "url": "https://www.bol.com/nl/p/nintendo-switch-oled-wit/9300000", "delivery": "Gratis verzending"},
    {"store": "MediaMarkt", "title": "Nintendo Switch OLED + Mario Kart 8 Deluxe", "price": "€ 359,00",
     "url": "https://www.mediamarkt.nl/switch-oled-mario", "delivery": "Verzendkosten € 4,95"},
    # Invented: this price is not on the page.
    {"store": "Coolblue", "title": "Nintendo Switch OLED Neon Rood/Blauw", "price": "€ 299,00"},
    # Invented: this title is not on the page.
    {"store": "Fnac", "title": "Sony PlayStation Portal Remote Player", "price": "€ 329,00"},
    # Wrong currency for the region.
    {"store": "Amazon", "title": "Nintendo Switch OLED Console - Wit", "price": "$319.00"},
]}


# -- extraction fallback ---------------------------------------------------------

def test_extraction_keeps_only_offers_that_are_on_the_page():
    text = page_text((PAGES / "new_layout.html").read_text(encoding="utf-8"))
    llm_helper, llm = helper(NEW_LAYOUT_ANSWER)
    offers = asyncio.run(llm_helper.extract_offers(text, "nintendo switch oled", NL))

    assert [(o.store, o.price, o.shipping_cost) for o in offers] == [("BOL", 319.0, 0.0), ("MEDIAMARKT", 359.0, 4.95)]
    assert all(o.extracted_by == "ai" for o in offers)
    assert offers[0].url.startswith("https://www.bol.com/")
    prompt, source, schema = llm.calls[0]
    assert schema is ExtractedOffers and "nintendo switch oled" in prompt and "Coolblue" in source


def test_extraction_failure_returns_nothing_instead_of_raising():
    llm_helper, _ = helper(RuntimeError("model unavailable"))
    assert asyncio.run(llm_helper.extract_offers("page", "x", US)) == []
    llm_helper, _ = helper({"offers": "not a list"})
    assert asyncio.run(llm_helper.extract_offers("page", "x", US)) == []


def test_wrapped_answers_are_unwrapped():
    text = page_text((PAGES / "new_layout.html").read_text(encoding="utf-8"))
    llm_helper, _ = helper({"content": NEW_LAYOUT_ANSWER})
    assert len(asyncio.run(llm_helper.extract_offers(text, "nintendo switch oled", NL))) == 2


@pytest.mark.parametrize("with_scrapegraph", [True, False])
def test_page_text_drops_scripts_and_keeps_links(monkeypatch, with_scrapegraph):
    if not with_scrapegraph:   # CI does not install ScrapeGraphAI
        monkeypatch.setitem(sys.modules, "scrapegraphai.utils.convert_to_md", None)
    text = page_text((PAGES / "known_layout.html").read_text(encoding="utf-8"))
    assert "window.noise" not in text and "https://www.walmart.com/ip/ps5-digital" in text
    assert "$449.00" in text


class FakePage:
    status = 200
    url = "https://www.google.com/search?tbm=shop"

    def __init__(self, html):
        self.html_content = html

    def find_by_regex(self, *args, **kwargs):
        return []          # the selectors find nothing, as after a layout change


def test_scraper_uses_fallback_only_when_selectors_find_nothing(monkeypatch):
    pytest.importorskip("scrapling")
    import scrapling.fetchers

    html = (PAGES / "new_layout.html").read_text(encoding="utf-8")

    async def fetch(*args, **kwargs):
        return FakePage(html)

    monkeypatch.setattr(scrapling.fetchers.StealthyFetcher, "async_fetch", staticmethod(fetch))

    llm_helper, llm = helper(NEW_LAYOUT_ANSWER)
    offers = asyncio.run(GoogleShoppingProvider(llm_helper).search("nintendo switch oled", NL))
    assert [o.store for o in offers] == ["BOL", "MEDIAMARKT"] and len(llm.calls) == 1

    off_helper, off_llm = helper(NEW_LAYOUT_ANSWER, fallback=False)
    assert asyncio.run(GoogleShoppingProvider(off_helper).search("nintendo switch oled", NL)) == []
    assert off_llm.calls == []
    assert asyncio.run(GoogleShoppingProvider().search("nintendo switch oled", NL)) == []


# -- second opinion on matching --------------------------------------------------

def listing(title, store="Shop", price=100.0):
    return Offer(store.upper(), title, price, f"${price}")


def test_review_rescues_and_rejects_but_never_overrides_hard_rules():
    offers = [
        listing("adidas Samba OG Shoes - White", "Adidas"),        # rules keep, AI agrees
        listing("adidas Samba OG Kids Trainers", "Schuh"),         # rules keep, AI rejects
        listing("Adidas Samba Original Gum Sole", "Size"),         # rules drop (no "og"), AI rescues
        listing("Replacement Laces for Adidas Samba OG", "eBay"),  # accessory: never sent
        listing("adidas Samba 2 OG", "Zalando"),                   # rules keep, AI gives no verdict
    ]
    score_offers("adidas samba og", offers)
    before = {o.title: o.relevance >= 0.7 for o in offers}
    assert before == {offers[0].title: True, offers[1].title: True, offers[2].title: False,
                      offers[3].title: False, offers[4].title: True}

    def answer(prompt, source, schema):
        assert schema is Verdicts and "Replacement Laces" not in source
        lines = dict(line.split(". ", 1) for line in source.splitlines())
        index = {title.split(" (sold by")[0]: int(i) for i, title in lines.items()}
        return {"verdicts": [
            {"index": index[offers[0].title], "same_product": True},
            {"index": index[offers[1].title], "same_product": False, "reason": "kids size"},
            {"index": index[offers[2].title], "same_product": True},
            {"index": 99, "same_product": True},                     # out of range: ignored
        ]}

    llm_helper, _ = helper(answer)
    changed = asyncio.run(llm_helper.review_matches("adidas samba og", offers, 0.7))
    ranked, _ = select_offers("adidas samba og", offers, min_relevance=0.7)

    assert changed == 2
    assert {o.store for o in ranked} == {"ADIDAS", "SIZE", "ZALANDO"}
    assert "ai_rejected" in offers[1].flags and "ai_confirmed" in offers[2].flags
    assert "ai_agreed" in offers[0].flags and offers[0].to_dict()["ai_checked"] is True
    assert offers[4].to_dict()["ai_checked"] is False


def test_review_failure_leaves_rules_result():
    offers = [listing("adidas Samba OG Kids Trainers")]
    score_offers("adidas samba og", offers)
    llm_helper, _ = helper(TimeoutError("slow"))
    assert asyncio.run(llm_helper.review_matches("adidas samba og", offers, 0.7)) == 0
    assert offers[0].relevance >= 0.7


def test_review_skips_the_call_when_nothing_is_borderline():
    offers = [listing("Silicone Case for iPhone 15")]
    llm_helper, llm = helper()
    score_offers("iphone 15", offers)
    assert asyncio.run(llm_helper.review_matches("iphone 15", offers, 0.7)) == 0
    assert llm.calls == []


def test_rank_offers_is_unchanged_rules_only():
    offers = [listing("adidas Samba OG Kids Trainers")]
    assert len(rank_offers("adidas samba og", offers)[0]) == 1


# -- configuration and wiring ----------------------------------------------------

def test_llm_is_off_unless_configured():
    base = load_settings()
    assert build_llm_helper(dataclasses.replace(base, llm_model="")) is None
    assert build_llm_helper(dataclasses.replace(base, llm_model="openai/x", llm_fallback=False, llm_judge=False)) is None
    on = build_llm_helper(dataclasses.replace(base, llm_model="ollama/llama3.2", llm_judge=False))
    assert on.options == LLMOptions(fallback=True, judge=False) and on.model == "ollama/llama3.2"


def test_graph_config():
    base = dataclasses.replace(load_settings(), llm_model="ollama/llama3.2", llm_api_key="",
                               llm_base_url="http://localhost:11434", llm_model_tokens=8192)
    assert graph_config(base) == {
        "llm": {"model": "ollama/llama3.2", "temperature": 0, "base_url": "http://localhost:11434",
                "model_tokens": 8192},
        "verbose": False, "headless": True,
    }


def test_search_api_reports_ai_involvement(settings, provider):
    provider.offers = [offer("Shop A", 20), offer("Shop B", 25, title="Acme Widget 3000 Mini")]
    llm_helper, llm = helper(lambda prompt, source, schema: {"verdicts": [
        {"index": i, "same_product": "Mini" not in line} for i, line in enumerate(source.splitlines())
    ]})
    with TestClient(create_app(settings, provider, llm=llm_helper)) as client:
        meta = client.get("/api/meta").json()
        assert meta["ai"] == {"model": "test/model", "fallback": True, "judge": True}
        body = client.post("/api/search", json={"product": "acme widget 3000"}).json()
    assert body["ai_changed"] == 0 and body["ai_extracted"] is False
    assert [r["store"] for r in body["results"]] == ["SHOP A"]
    assert len(llm.calls) == 1


def test_search_api_without_ai(client):
    assert client.get("/api/meta").json()["ai"] == {"model": None, "fallback": False, "judge": False}
    assert client.post("/api/search", json={"product": "acme widget 3000"}).json()["ai_changed"] is None


# -- eval comparison mode --------------------------------------------------------

def test_ai_eval_mode_runs_and_gates(capsys):
    pytest.importorskip("scrapling")

    def judge_everything_same(prompt, source, schema):
        if schema is Verdicts:
            return {"verdicts": [{"index": i, "same_product": True} for i in range(len(source.splitlines()))]}
        return {"offers": []}

    always_yes = LLMHelper(judge_everything_same, LLMOptions(), model="test/yes")
    # Saying "same product" to everything keeps variants the rules dropped: the gate must catch it.
    assert evals.main(["--ai"], llm=always_yes) == 1
    out = capsys.readouterr().out
    assert "AI comparison using test/yes" in out and "new_layout.html" in out and "FAIL" in out

    def judge_nothing(prompt, source, schema):
        return {"verdicts": []} if schema is Verdicts else {"offers": []}

    silent = LLMHelper(judge_nothing, LLMOptions(), model="test/silent")
    assert evals.main(["--ai"], llm=silent) == 0      # no opinions: identical to rules alone


def test_ai_eval_mode_needs_a_model(monkeypatch, capsys):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert evals.main(["--ai"]) == 2
    assert "LLM_MODEL" in capsys.readouterr().out
