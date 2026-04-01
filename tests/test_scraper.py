"""Tests for scraper navigation helpers."""

from types import SimpleNamespace

from cryptopanic_scraper.scraper import (
    CryptoPanicScraper,
    _detect_blocking_page,
    _feed_state_changed,
    _load_more_looks_stuck,
)


def test_detect_blocking_page_cloudflare_title_and_markup():
    html = """
    <html>
      <head><title>Just a moment...</title></head>
      <body>cloudflare challenge-platform</body>
    </html>
    """
    assert _detect_blocking_page("Just a moment...", html) == "Cloudflare challenge page"


def test_detect_blocking_page_cloudflare_marker_only():
    html = "<html><body>challenge-platform</body></html>"
    assert _detect_blocking_page("Loading", html) == "Cloudflare anti-bot challenge"


def test_detect_blocking_page_none_for_normal_page():
    html = "<html><head><title>CryptoPanic</title></head><body>news rows</body></html>"
    assert _detect_blocking_page("CryptoPanic", html) is None


def test_feed_state_changed_by_count():
    before = {"count": 10, "last_date": "a", "last_href": "x"}
    after = {"count": 12, "last_date": "a", "last_href": "x"}
    assert _feed_state_changed(before, after) is True


def test_feed_state_changed_by_tail_identity():
    before = {"count": 10, "last_date": "a", "last_href": "x"}
    after = {"count": 10, "last_date": "b", "last_href": "y"}
    assert _feed_state_changed(before, after) is True


def test_feed_state_changed_false_when_identical():
    state = {"count": 10, "last_date": "a", "last_href": "x"}
    assert _feed_state_changed(state, dict(state)) is False


def test_load_more_looks_stuck_true_for_loading_spinner_button():
    state = {
        "present": True,
        "text": "Loading...",
        "disabled": True,
        "aria_disabled": False,
        "class_name": "btn spinner-border",
        "has_spinner": True,
    }
    assert _load_more_looks_stuck(state) is True


def test_load_more_looks_stuck_false_for_normal_button():
    state = {
        "present": True,
        "text": "Load More",
        "disabled": False,
        "aria_disabled": False,
        "class_name": "btn",
        "has_spinner": False,
    }
    assert _load_more_looks_stuck(state) is False


def test_maybe_reuse_attached_feed_when_rows_present():
    args = SimpleNamespace(
        filter="all",
        category=None,
        start_date=None,
        end_date="2026-04-01",
        checkpoint_interval=50,
        output_dir="data",
        resume=False,
        debugger_address="127.0.0.1:9222",
        headless=False,
    )
    scraper = CryptoPanicScraper(args)

    class Driver:
        current_url = "https://www.cryptopanic.com/news?filter=all"
        title = "CryptoPanic"
        page_source = "<html></html>"

        def find_elements(self, by, selector):
            return [object()] if selector == "div.news-row:not(.news-row-sponsored)" else []

        def execute_script(self, script):
            return None

    scraper.driver = Driver()
    assert scraper._maybe_reuse_attached_feed("https://www.cryptopanic.com/news?filter=all") is True
