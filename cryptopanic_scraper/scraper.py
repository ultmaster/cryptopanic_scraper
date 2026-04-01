"""Main scraper class encapsulating all Selenium logic."""

import logging
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from . import config
from .checkpoint import CheckpointManager
from .models import Article
from .storage import JSONLWriter
from .utils import resolve_urls_batch, retry

logger = logging.getLogger("cryptopanic")


class CryptoPanicScraper:
    def __init__(self, args):
        self.args = args
        self.driver = None
        self.checkpoint = CheckpointManager(
            filter_type=args.filter,
            start_date=args.start_date,
            end_date=args.end_date,
            interval=args.checkpoint_interval,
        )
        self.writer = JSONLWriter(
            output_dir=args.output_dir,
            filter_type=args.filter,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        self._driver_reconnects = 0
        self._scrape_start_time = None

    # ------------------------------------------------------------------ #
    #  Driver lifecycle
    # ------------------------------------------------------------------ #

    def setup_driver(self):
        """Create and configure Chrome WebDriver."""
        options = webdriver.ChromeOptions()
        if self.args.headless:
            options.add_argument("--headless")
        options.add_argument("--window-size=1200,800")
        options.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.images": 2},
        )
        # Stability for long scrapes
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")

        logger.info("Initializing ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        logger.info("ChromeDriver ready.")

    def teardown(self):
        """Close the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            logger.info("ChromeDriver closed.")

    def navigate_to_feed(self):
        """Navigate to the CryptoPanic news feed."""
        url = f"{config.BASE_URL}?filter={self.args.filter}"
        logger.info("Navigating to %s", url)
        self.driver.get(url)
        WebDriverWait(self.driver, config.PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, config.SELECTORS["news_row"])
            )
        )
        logger.info("Page loaded successfully.")

    def _reconnect_driver(self):
        """Tear down and recreate driver after a crash."""
        self._driver_reconnects += 1
        if self._driver_reconnects > config.MAX_DRIVER_RECONNECTS:
            logger.critical(
                "Max driver reconnects (%d) exceeded.",
                config.MAX_DRIVER_RECONNECTS,
            )
            raise RuntimeError("Too many driver crashes")
        logger.warning(
            "Reconnecting driver (attempt %d/%d)...",
            self._driver_reconnects, config.MAX_DRIVER_RECONNECTS,
        )
        self.checkpoint.save()
        self.teardown()
        time.sleep(10)
        self.setup_driver()
        self.navigate_to_feed()
        self._restore_scroll_position()

    # ------------------------------------------------------------------ #
    #  Scroll / pagination
    # ------------------------------------------------------------------ #

    def _restore_scroll_position(self):
        """After driver reconnect or resume, click Load More to restore position."""
        target_pages = self.checkpoint.pages_loaded
        if target_pages == 0:
            return
        logger.info(
            "Restoring scroll position: clicking Load More %d times...",
            target_pages,
        )
        for i in range(target_pages):
            try:
                self._click_load_more()
                if (i + 1) % 50 == 0:
                    logger.info("  Restored %d/%d pages...", i + 1, target_pages)
            except Exception as e:
                logger.warning(
                    "Failed to restore page %d: %s. Continuing from here.", i + 1, e,
                )
                break
        logger.info("Scroll position restored to page %d.", self.checkpoint.pages_loaded)

    @retry(max_attempts=config.MAX_PAGE_RETRIES, backoff_base=config.RETRY_BACKOFF_BASE)
    def _click_load_more(self):
        """Click the 'Load More' button once and wait for new content."""
        btn = WebDriverWait(self.driver, config.PAGE_LOAD_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.CLASS_NAME, config.SELECTORS["load_more"])
            )
        )
        before_count = len(
            self.driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", btn,
        )
        time.sleep(0.3)
        btn.click()
        time.sleep(config.SCROLL_PAUSE)

        # Wait for new elements to appear
        WebDriverWait(self.driver, config.PAGE_LOAD_TIMEOUT).until(
            lambda d: len(
                d.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
            ) > before_count
        )
        after_count = len(
            self.driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
        )
        logger.debug(
            "Load More: %d -> %d articles (+%d)",
            before_count, after_count, after_count - before_count,
        )

    # ------------------------------------------------------------------ #
    #  Extraction
    # ------------------------------------------------------------------ #

    def _extract_batch_from_dom(self) -> list[dict]:
        """Run bulk JS extraction to get all articles currently in the DOM."""
        raw_articles = self.driver.execute_script(config.EXTRACT_ARTICLES_JS)
        logger.debug("JS extraction returned %d articles from DOM.", len(raw_articles))
        return raw_articles

    def _retry_incomplete_rows(self, raw_list: list[dict]) -> list[dict]:
        """Scroll incomplete rows into view and re-extract them.

        CryptoPanic lazy-renders some rows; scrolling into view forces the
        browser to populate their text content.
        """
        incomplete_indices = [
            raw["idx"] for raw in raw_list
            if not raw.get("title") and raw.get("idx") is not None
        ]
        if not incomplete_indices:
            return raw_list

        logger.info(
            "Retrying %d rows with missing title (lazy rendering)...",
            len(incomplete_indices),
        )
        # Scroll each incomplete row into view and re-extract
        retry_js = """
        const indices = arguments[0];
        const rows = document.querySelectorAll('div.news-row.news-row-link');
        const results = [];
        for (const idx of indices) {
            if (idx >= rows.length) continue;
            const el = rows[idx];
            el.scrollIntoView({block: 'center'});
            // Allow a brief layout pass
            const titleEl = el.querySelector('span.title-text span:first-child');
            results.push({
                idx: idx,
                datetime: el.querySelector('time')?.getAttribute('datetime'),
                title: titleEl ? titleEl.textContent.trim() : '',
                href: el.querySelector('a.news-cell.nc-title')?.href || '',
                source: el.querySelector('span.si-source-name')?.textContent?.trim() || '',
                currencies: Array.from(el.querySelectorAll('.colored-link')).map(c => c.textContent.trim()),
                votes: {}
            });
        }
        return results;
        """
        retried = self.driver.execute_script(retry_js, incomplete_indices)

        # Merge retried rows back into raw_list
        retried_by_idx = {r["idx"]: r for r in retried if r.get("title")}
        for i, raw in enumerate(raw_list):
            if raw["idx"] in retried_by_idx:
                raw_list[i] = retried_by_idx[raw["idx"]]

        return raw_list

    def _raw_to_articles(self, raw_list: list[dict]) -> list[Article]:
        """Convert raw JS-extracted dicts into Article objects.

        Rows that are still missing required fields after retry are recorded
        as failed and skipped.
        """
        articles = []
        for raw in raw_list:
            if not raw.get("datetime") or not raw.get("title"):
                logger.warning(
                    "Dropping row %s: missing date or title after retry: %s",
                    raw.get("idx"), raw,
                )
                self.checkpoint.add_failed({
                    "idx": raw.get("idx"),
                    "reason": "missing date or title after retry",
                    "raw": raw,
                })
                continue
            votes = {}
            if isinstance(raw.get("votes"), dict):
                votes = raw["votes"]
            articles.append(Article(
                date=raw["datetime"],
                title=raw["title"],
                currencies=raw.get("currencies", []),
                votes=votes,
                source_name=raw.get("source", ""),
                source_url="",
                cryptopanic_url=raw.get("href", ""),
            ))
        return articles

    def _resolve_article_urls(self, articles: list[Article]):
        """Resolve CryptoPanic redirect URLs to actual source URLs in parallel."""
        if self.args.no_resolve_urls:
            logger.info("URL resolution skipped (--no-resolve-urls).")
            return

        url_map = {}
        for i, a in enumerate(articles):
            if a.cryptopanic_url and not a.source_url:
                url_map[i] = a.cryptopanic_url

        if not url_map:
            return

        logger.info("Resolving %d source URLs...", len(url_map))

        # Pass browser cookies to requests for authenticated redirects
        cookies = {}
        try:
            for c in self.driver.get_cookies():
                cookies[c["name"]] = c["value"]
        except Exception:
            pass

        resolved = resolve_urls_batch(
            url_map,
            max_workers=config.URL_RESOLVE_WORKERS,
            timeout=config.URL_RESOLVE_TIMEOUT,
            cookies=cookies,
        )
        for idx, url in resolved.items():
            articles[idx].source_url = url

        success = sum(1 for u in resolved.values() if u)
        logger.info("Resolved %d/%d URLs successfully.", success, len(url_map))

    # ------------------------------------------------------------------ #
    #  Date filtering
    # ------------------------------------------------------------------ #

    def _is_before_start_date(self, iso_date: str) -> bool:
        if not self.args.start_date:
            return False
        return iso_date[:10] < self.args.start_date

    def _is_after_end_date(self, iso_date: str) -> bool:
        if not self.args.end_date:
            return False
        return iso_date[:10] > self.args.end_date

    def _filter_by_date(self, articles: list[Article]) -> list[Article]:
        """Filter articles to only those within the date range."""
        return [
            a for a in articles
            if not self._is_before_start_date(a.date)
            and not self._is_after_end_date(a.date)
        ]

    # ------------------------------------------------------------------ #
    #  Progress logging
    # ------------------------------------------------------------------ #

    def _log_progress(self):
        """Log current scraping progress with optional ETA."""
        total = len(self.checkpoint.articles)
        elapsed = 0.0
        if self._scrape_start_time:
            elapsed = (datetime.now() - self._scrape_start_time).total_seconds()
        rate = total / elapsed * 60 if elapsed > 0 else 0

        msg = (
            f"Progress: {total} articles, "
            f"{self.checkpoint.pages_loaded} pages, "
            f"oldest={self.checkpoint.oldest_date or 'N/A'}, "
            f"rate={rate:.0f}/min"
        )

        # ETA estimation when we have a start_date target
        if (
            self.args.start_date
            and self.checkpoint.oldest_date
            and self._scrape_start_time
        ):
            try:
                oldest = datetime.fromisoformat(
                    self.checkpoint.oldest_date.replace("Z", "+00:00")
                )
                target = datetime.fromisoformat(
                    self.args.start_date + "T00:00:00+00:00"
                )
                now_dt = datetime.now(oldest.tzinfo) if oldest.tzinfo else datetime.now()
                date_progress = (now_dt - oldest).total_seconds()
                date_remaining = (oldest - target).total_seconds()
                if date_progress > 0 and elapsed > 0:
                    eta_seconds = (date_remaining / date_progress) * elapsed
                    eta_hours = eta_seconds / 3600
                    msg += f", ETA~{eta_hours:.1f}h"
            except Exception:
                pass

        logger.info(msg)

    # ------------------------------------------------------------------ #
    #  Main run loop
    # ------------------------------------------------------------------ #

    def run(self):
        """Main entry point: load pages, extract, save."""
        self._scrape_start_time = datetime.now()

        # Resume from checkpoint if requested
        if self.args.resume and self.checkpoint.load():
            # Checkpoint articles are already persisted in the JSONL file from
            # the previous run.  Do NOT re-add them to the writer — that would
            # duplicate records.  The writer already counted existing lines in
            # its __init__, so total_written is accurate.
            pass

        self.checkpoint.register_signal_handlers()
        self.setup_driver()
        self.navigate_to_feed()

        # Restore scroll position if resuming
        if self.args.resume and self.checkpoint.pages_loaded > 0:
            self._restore_scroll_position()

        try:
            self._loading_phase()
            self._extraction_phase()
        except SystemExit:
            logger.info("Graceful shutdown.")
        except Exception as e:
            logger.critical("Fatal error: %s", e, exc_info=True)
            self.checkpoint.save()
            raise
        finally:
            self.writer.finalize()
            self.teardown()

    def _loading_phase(self):
        """Click 'Load More' until we have enough articles or reach start_date."""
        logger.info("=== Loading Phase: expanding news feed ===")
        consecutive_failures = 0

        while True:
            # Check article limit
            element_count = len(
                self.driver.find_elements(
                    By.CSS_SELECTOR, config.SELECTORS["news_row"]
                )
            )
            if self.args.limit and element_count >= self.args.limit:
                logger.info(
                    "Reached article limit (%d). Stopping load phase.",
                    self.args.limit,
                )
                break

            # Check if we've scrolled past start_date
            if self.args.start_date:
                last_date = self.driver.execute_script("""
                    const rows = document.querySelectorAll('div.news-row.news-row-link');
                    if (rows.length === 0) return null;
                    const last = rows[rows.length - 1];
                    const t = last.querySelector('time');
                    return t ? t.getAttribute('datetime') : null;
                """)
                if last_date and self._is_before_start_date(last_date):
                    logger.info(
                        "Oldest visible article (%s) is before start date (%s). "
                        "Stopping load phase.",
                        last_date[:10], self.args.start_date,
                    )
                    break

            # Click Load More
            try:
                self._click_load_more()
                self.checkpoint.increment_pages()
                consecutive_failures = 0

                # Periodic progress during loading
                if self.checkpoint.pages_loaded % 10 == 0:
                    logger.info(
                        "Pages loaded: %d, articles visible: %d",
                        self.checkpoint.pages_loaded, element_count,
                    )
                if self.checkpoint.pages_loaded % 50 == 0:
                    self.checkpoint.save()

            except TimeoutException:
                consecutive_failures += 1
                if consecutive_failures >= config.MAX_PAGE_RETRIES:
                    logger.warning(
                        "No more content to load (consecutive timeouts). "
                        "Moving to extraction."
                    )
                    break
                logger.warning(
                    "Load More timeout (%d/%d)",
                    consecutive_failures, config.MAX_PAGE_RETRIES,
                )

            except WebDriverException as e:
                logger.error("WebDriver error during loading: %s", e)
                try:
                    self._reconnect_driver()
                except RuntimeError:
                    break

        logger.info(
            "Loading complete. Pages loaded: %d", self.checkpoint.pages_loaded,
        )

    def _extraction_phase(self):
        """Extract all articles from the DOM, resolve URLs, save."""
        logger.info("=== Extraction Phase: reading article data ===")

        raw_articles = self._extract_batch_from_dom()
        raw_articles = self._retry_incomplete_rows(raw_articles)
        articles = self._raw_to_articles(raw_articles)
        logger.info("Extracted %d articles from DOM.", len(articles))

        # Filter by date range
        if self.args.start_date or self.args.end_date:
            before = len(articles)
            articles = self._filter_by_date(articles)
            logger.info(
                "Date filter: %d -> %d articles (range: %s to %s)",
                before, len(articles), self.args.start_date, self.args.end_date,
            )

        # Apply limit
        if self.args.limit and len(articles) > self.args.limit:
            articles = articles[: self.args.limit]
            logger.info("Applied limit: %d articles.", self.args.limit)

        # Resolve source URLs (parallel, via requests)
        self._resolve_article_urls(articles)

        # Add to checkpoint and writer (with dedup)
        new_count = 0
        for article in articles:
            article_dict = article.to_dict()
            if self.checkpoint.add_article(article_dict):
                self.writer.add(article_dict)
                new_count += 1

        self.writer.flush()
        self.checkpoint.save()
        self._log_progress()
        logger.info(
            "Extraction complete. %d new articles added (%d total).",
            new_count, len(self.checkpoint.articles),
        )
