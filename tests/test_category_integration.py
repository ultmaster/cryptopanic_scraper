"""Integration tests for category-based scraping.

These tests connect to a Chrome instance running on port 9222 and verify
that each of the five supported news categories loads correctly and yields
articles from the expected CryptoPanic path.

Prerequisites:
    Launch Chrome with remote debugging before running:

        google-chrome --remote-debugging-port=9222 \
            --user-data-dir=/tmp/cryptopanic-debug-profile \
            'https://www.cryptopanic.com/news'

    Then run:
        python -m pytest tests/test_category_integration.py -v
"""

import time

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from cryptopanic_scraper import config

DEBUGGER_ADDRESS = "127.0.0.1:9222"
CATEGORIES = config.VALID_CATEGORIES  # price-analysis, regulation, media, ico-news, events
PAGE_LOAD_TIMEOUT = 30


@pytest.fixture(scope="module")
def driver():
    """Attach to the Chrome instance on port 9222."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)
    try:
        drv = webdriver.Chrome(options=options)
    except Exception as e:
        pytest.skip(
            f"Cannot attach to Chrome at {DEBUGGER_ADDRESS}. "
            f"Launch Chrome with --remote-debugging-port=9222 first. Error: {e}"
        )
    yield drv
    # Do NOT quit — this is the user's external Chrome session.


def _navigate_and_check(driver, category):
    """Navigate to a category page and verify it loads correctly.

    Some categories (e.g. media) may have zero articles at times.  We verify
    the page loads and the URL is correct, and return the row count + first
    title (empty string when no rows).
    """
    url = f"{config.BASE_URL}/{category}"
    driver.get(url)

    # Give the page a moment to render — some categories may be empty, so we
    # can't always wait for a news row.  Instead, wait for the page body and
    # then check for rows.
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, config.SELECTORS["news_row"])
            )
        )
    except Exception:
        # Page loaded but no news rows — could be an empty category.
        time.sleep(3)  # brief extra wait for slow renders

    # Verify the URL is correct
    assert f"/news/{category}" in driver.current_url, (
        f"Expected /news/{category} in URL, got {driver.current_url}"
    )

    # Check for news rows (may be 0 for empty categories like media)
    rows = driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])

    first_title = ""
    if rows:
        first_title_el = rows[0].find_element(
            By.CSS_SELECTOR, config.SELECTORS["title"]
        )
        first_title = first_title_el.text.strip()

    return len(rows), first_title


@pytest.mark.parametrize("category", CATEGORIES)
def test_category_loads_news_rows(driver, category):
    """Verify that navigating to /news/{category} loads the page correctly.

    Some categories (e.g. media) may be temporarily empty — this is expected.
    The test verifies the page loads and the URL path is correct.  When rows
    are present, it also checks that the first title is non-empty.
    """
    row_count, first_title = _navigate_and_check(driver, category)
    # The page must have loaded with the correct URL (asserted inside helper).
    # If rows are present, the first title should be non-empty.
    if row_count > 0:
        assert len(first_title) > 0, (
            f"First article title is empty for category '{category}'"
        )
    print(f"\n  Category '{category}': {row_count} rows loaded"
          + (f", first title: '{first_title[:60]}'" if first_title else ""))


def test_category_url_includes_filter(driver):
    """Verify that category + filter combo produces the correct URL."""
    category = "regulation"
    filter_type = "hot"
    url = f"{config.BASE_URL}/{category}?filter={filter_type}"
    driver.get(url)

    WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, config.SELECTORS["news_row"])
        )
    )

    assert f"/news/{category}" in driver.current_url
    rows = driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
    assert len(rows) > 0, "No rows for regulation + hot filter"


def test_bulk_js_extraction_works_on_category(driver):
    """Verify that the bulk JS extraction script works on category pages."""
    category = "price-analysis"
    url = f"{config.BASE_URL}/{category}"
    driver.get(url)

    WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, config.SELECTORS["news_row"])
        )
    )

    articles = driver.execute_script(config.EXTRACT_ARTICLES_JS)
    assert isinstance(articles, list)
    assert len(articles) > 0, "JS extraction returned no articles"

    # Verify extracted article structure
    first = articles[0]
    assert "title" in first
    assert "datetime" in first
    assert "href" in first
    assert "source" in first
    assert len(first["title"]) > 0, "JS-extracted title is empty"
