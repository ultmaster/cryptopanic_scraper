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
from .utils import download_article_content_batch, resolve_urls_batch, retry

logger = logging.getLogger("cryptopanic")


def _detect_blocking_page(page_title: str, page_source: str) -> str | None:
    """Identify known anti-bot / blocking pages before Selenium times out."""
    title = (page_title or "").strip().lower()
    source = (page_source or "").lower()

    if "just a moment" in title and "cloudflare" in source:
        return "Cloudflare challenge page"
    if "challenge-platform" in source or "cf-browser-verification" in source:
        return "Cloudflare anti-bot challenge"
    if "access denied" in title and "cloudflare" in source:
        return "Cloudflare access denied page"
    return None


def _feed_state_changed(before_state: dict, after_state: dict) -> bool:
    """Detect whether the visible feed progressed after clicking Load More."""
    if after_state["count"] > before_state["count"]:
        return True
    if after_state["last_date"] != before_state["last_date"]:
        return True
    if after_state["last_href"] != before_state["last_href"]:
        return True
    return False


def _load_more_looks_stuck(button_state: dict) -> bool:
    """Heuristic for a Load More button stuck in a loading spinner state."""
    text = (button_state.get("text") or "").strip().lower()
    class_name = (button_state.get("class_name") or "").lower()
    return bool(
        button_state.get("present")
        and (button_state.get("disabled") or button_state.get("aria_disabled"))
        and (
            "loading" in text
            or "spinner" in class_name
            or button_state.get("has_spinner")
        )
    )


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
            resume=args.resume,
        )
        self._driver_reconnects = 0
        self._scrape_start_time = None

    # ------------------------------------------------------------------ #
    #  Driver lifecycle
    # ------------------------------------------------------------------ #

    def setup_driver(self):
        """Create and configure Chrome WebDriver."""
        options = webdriver.ChromeOptions()

        logger.info("Initializing ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        if self.args.debugger_address:
            logger.info(
                "Attaching to existing Chrome at %s...",
                self.args.debugger_address,
            )
            options.add_experimental_option(
                "debuggerAddress", self.args.debugger_address,
            )
        else:
            if self.args.headless:
                options.add_argument("--headless")
            options.add_argument("--window-size=1200,800")
            options.add_experimental_option(
                "prefs", {"profile.managed_default_content_settings.images": 2},
            )
            # Stability for long scrapes
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
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

    @retry(
        max_attempts=config.MAX_PAGE_RETRIES,
        backoff_base=config.RETRY_BACKOFF_BASE,
        exceptions=(TimeoutException, WebDriverException),
    )
    def navigate_to_feed(self):
        """Navigate to the CryptoPanic news feed."""
        url = f"{config.BASE_URL}?filter={self.args.filter}"
        if self._maybe_reuse_attached_feed(url):
            return

        logger.info("Navigating to %s", url)
        self.driver.get(url)
        try:
            WebDriverWait(self.driver, config.PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, config.SELECTORS["news_row"])
                )
            )
        except TimeoutException:
            page_title = ""
            page_source = ""
            current_url = ""
            try:
                page_title = self.driver.title
                page_source = self.driver.page_source
                current_url = self.driver.current_url
            except Exception:
                pass

            block_reason = _detect_blocking_page(page_title, page_source)
            if block_reason:
                if self.args.headless:
                    raise RuntimeError(
                        "CryptoPanic returned a blocking page instead of the feed "
                        f"({block_reason}) at {current_url or url}. "
                        "This machine or session is being challenged, so Selenium "
                        "cannot reach the news rows."
                    )
                self._wait_for_manual_challenge_resolution(
                    url=current_url or url,
                    block_reason=block_reason,
                )
                page_title = self.driver.title
                current_url = self.driver.current_url
                logger.info(
                    "Challenge cleared. Current title=%r url=%s",
                    page_title, current_url or url,
                )
                logger.info("Page loaded successfully.")
                return

            logger.warning(
                "Timed out waiting for news rows. Current title=%r url=%s",
                page_title, current_url or url,
            )
            raise
        # Remove the sign-in blur overlay that blocks interaction
        self.driver.execute_script(
            'document.querySelectorAll(".blur-overlay").forEach(e => e.remove());'
        )
        logger.info("Page loaded successfully.")

    def _maybe_reuse_attached_feed(self, url: str) -> bool:
        """Reuse the current page when attached to an existing Chrome session."""
        if not self.args.debugger_address:
            return False

        current_url = ""
        page_title = ""
        page_source = ""
        try:
            current_url = self.driver.current_url or ""
            page_title = self.driver.title or ""
            page_source = self.driver.page_source or ""
        except Exception:
            return False

        if self.driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"]):
            logger.info(
                "Attached browser already has the CryptoPanic feed loaded at %s. "
                "Reusing the current page without navigating.",
                current_url or url,
            )
            self.driver.execute_script(
                'document.querySelectorAll(".blur-overlay").forEach(e => e.remove());'
            )
            logger.info("Page loaded successfully.")
            return True

        if current_url.startswith(config.BASE_URL):
            block_reason = _detect_blocking_page(page_title, page_source)
            if block_reason and not self.args.headless:
                logger.info(
                    "Attached browser is already on a challenge page at %s. "
                    "Waiting for manual resolution without refreshing.",
                    current_url,
                )
                self._wait_for_manual_challenge_resolution(
                    url=current_url,
                    block_reason=block_reason,
                )
                self.driver.execute_script(
                    'document.querySelectorAll(".blur-overlay").forEach(e => e.remove());'
                )
                logger.info("Page loaded successfully.")
                return True

        return False

    def _wait_for_manual_challenge_resolution(self, url: str, block_reason: str):
        """Keep a headed browser open so the user can solve a site challenge."""
        timeout = max(0, int(getattr(self.args, "manual_challenge_timeout", 0) or 0))
        if timeout == 0:
            raise RuntimeError(
                "CryptoPanic returned a blocking page instead of the feed "
                f"({block_reason}) at {url}. "
                "Run without --headless and set --manual-challenge-timeout to "
                "allow time for manual intervention."
            )

        logger.warning(
            "CryptoPanic returned %s at %s. Browser will stay open for up to "
            "%ds so you can solve the challenge manually.",
            block_reason, url, timeout,
        )
        WebDriverWait(self.driver, timeout, poll_frequency=1).until(
            lambda d: bool(
                d.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
            )
        )

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

    def _click_load_more(self):
        """Click the 'Load More' button once and wait for new content."""
        # Use presence (not clickable) — the button is valid but far below the
        # viewport, so Selenium considers it "not displayed / not clickable".
        btn = WebDriverWait(self.driver, config.PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "button.btn-outline-primary")
            )
        )
        before_state = self._get_feed_state()
        # Scroll into view and click via JavaScript to bypass overlay / viewport issues
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
            btn,
        )
        time.sleep(config.SCROLL_PAUSE)

        after_state = self._wait_for_feed_progress(
            before_state,
            timeout=config.PAGE_LOAD_TIMEOUT,
        )
        if not _feed_state_changed(before_state, after_state):
            button_state = self._get_load_more_button_state()
            if _load_more_looks_stuck(button_state):
                logger.warning(
                    "Load More appears stuck in a greyed-out loading state; "
                    "attempting a revive click before timing out.",
                )
                self._revive_stuck_load_more()
            else:
                logger.warning(
                    "Load More showed no visible progress within %ss; waiting an "
                    "extra %ss before treating it as a timeout.",
                    config.PAGE_LOAD_TIMEOUT, config.LOAD_MORE_GRACE_TIMEOUT,
                )
            after_state = self._wait_for_feed_progress(
                before_state,
                timeout=config.LOAD_MORE_GRACE_TIMEOUT,
            )
        if not _feed_state_changed(before_state, after_state):
            raise TimeoutException(
                "Load More did not change the visible feed before timeout."
            )

        logger.debug(
            "Load More: %d -> %d articles (+%d)",
            before_state["count"], after_state["count"],
            after_state["count"] - before_state["count"],
        )

    def _get_feed_state(self) -> dict:
        """Capture enough feed state to notice progress after Load More."""
        rows = self.driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
        state = {
            "count": len(rows),
            "last_date": "",
            "last_href": "",
        }
        if not rows:
            return state

        last_row = rows[-1]
        try:
            time_el = last_row.find_element(By.CSS_SELECTOR, config.SELECTORS["time"])
            state["last_date"] = time_el.get_attribute("datetime") or ""
        except Exception:
            pass
        try:
            link_el = last_row.find_element(
                By.CSS_SELECTOR, config.SELECTORS["article_link"]
            )
            state["last_href"] = link_el.get_attribute("href") or ""
        except Exception:
            pass
        return state

    def _wait_for_feed_progress(self, before_state: dict, timeout: float) -> dict:
        """Poll the feed until it visibly progresses or the timeout expires."""
        end_time = time.time() + timeout
        last_state = before_state
        while time.time() < end_time:
            try:
                current_state = self._get_feed_state()
            except WebDriverException:
                time.sleep(config.LOAD_MORE_POLL_INTERVAL)
                continue
            last_state = current_state
            if _feed_state_changed(before_state, current_state):
                return current_state
            time.sleep(config.LOAD_MORE_POLL_INTERVAL)
        return last_state

    def _get_load_more_button_state(self) -> dict:
        """Read the current Load More button state from the DOM."""
        return self.driver.execute_script("""
            const btn = document.querySelector('button.btn-outline-primary');
            if (!btn) {
                return {
                    present: false,
                    text: '',
                    disabled: false,
                    aria_disabled: false,
                    class_name: '',
                    has_spinner: false
                };
            }
            return {
                present: true,
                text: (btn.innerText || btn.textContent || '').trim(),
                disabled: !!btn.disabled,
                aria_disabled: (btn.getAttribute('aria-disabled') || '').toLowerCase() === 'true',
                class_name: btn.className || '',
                has_spinner: !!btn.querySelector('.spinner-border, .spinner-grow, .spinner, [class*="spinner"]')
            };
        """)

    def _revive_stuck_load_more(self):
        """Try to unstick a greyed-out Loading button by forcing a fresh click."""
        self.driver.execute_script("""
            const btn = document.querySelector('button.btn-outline-primary');
            if (!btn) return false;
            btn.scrollIntoView({block: 'center'});
            btn.disabled = false;
            btn.removeAttribute('disabled');
            btn.setAttribute('aria-disabled', 'false');
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(type => {
                btn.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
            });
            return true;
        """)
        time.sleep(config.SCROLL_PAUSE)

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
                datetime: (() => { try { const t = el.querySelector('time'); return t ? new Date(t.getAttribute('datetime')).toISOString() : null; } catch(e) { return null; } })(),
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
        if success == 0 and len(url_map) > 0:
            logger.warning(
                "Could not resolve any source URLs. CryptoPanic may require "
                "authentication for redirects. Use --no-resolve-urls to skip. "
                "Source names and CryptoPanic URLs are still captured."
            )
        else:
            logger.info("Resolved %d/%d URLs successfully.", success, len(url_map))

    def _download_article_content(self, articles: list[Article]):
        """Download readable article text from resolved publisher URLs."""
        if not self.args.download_content:
            return
        if self.args.no_resolve_urls:
            logger.warning(
                "Content download requested, but --no-resolve-urls is set. "
                "Skipping article content extraction."
            )
            return

        url_map = {}
        for i, article in enumerate(articles):
            if article.source_url and not article.content_text:
                url_map[i] = article.source_url

        if not url_map:
            logger.info("No resolved source URLs available for content download.")
            return

        logger.info("Downloading article content for %d source pages...", len(url_map))
        content_map = download_article_content_batch(
            url_map,
            max_workers=config.CONTENT_FETCH_WORKERS,
            timeout=config.CONTENT_FETCH_TIMEOUT,
            max_chars=self.args.content_max_chars,
        )
        for idx, content_text in content_map.items():
            articles[idx].content_text = content_text

        success = sum(1 for content in content_map.values() if content)
        logger.info("Downloaded readable content for %d/%d articles.", success, len(url_map))

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

    def _remaining_limit(self) -> int | None:
        if not self.args.limit:
            return None
        remaining = self.args.limit - len(self.checkpoint.articles)
        return max(remaining, 0)

    def _extract_visible_articles(self) -> list[Article]:
        """Extract and date-filter all currently visible rows from the DOM."""
        raw_articles = self._extract_batch_from_dom()
        raw_articles = self._retry_incomplete_rows(raw_articles)
        articles = self._raw_to_articles(raw_articles)

        if self.args.start_date or self.args.end_date:
            before = len(articles)
            articles = self._filter_by_date(articles)
            logger.info(
                "Date filter on visible rows: %d -> %d articles (range: %s to %s)",
                before, len(articles), self.args.start_date, self.args.end_date,
            )

        return articles

    def _persist_articles(self, articles: list[Article], context: str) -> int:
        """Resolve, enrich, deduplicate, and write articles."""
        new_articles = [
            article for article in articles
            if article.dedup_key not in self.checkpoint.seen_keys
        ]

        remaining = self._remaining_limit()
        if remaining == 0:
            logger.info("Article limit already reached; skipping %s persistence.", context)
            return 0
        if remaining is not None:
            new_articles = new_articles[:remaining]

        if not new_articles:
            logger.info("No new articles to persist during %s.", context)
            return 0

        self._resolve_article_urls(new_articles)
        self._download_article_content(new_articles)

        new_count = 0
        for article in new_articles:
            article_dict = article.to_dict()
            if self.checkpoint.add_article(article_dict):
                self.writer.add(article_dict)
                new_count += 1
                logger.debug(
                    "[%d] %s | %s | %s",
                    len(self.checkpoint.articles), article.date[:19],
                    article.source_name, article.title[:80],
                )

        self.writer.flush()
        self.checkpoint.save()
        self._log_progress()
        logger.info("%s persisted %d new articles.", context, new_count)
        return new_count

    def _extract_and_persist_visible_articles(self, context: str) -> int:
        """Run extraction against the current DOM and persist unseen matches."""
        logger.info("=== Extraction: %s ===", context)
        articles = self._extract_visible_articles()

        if articles:
            newest = articles[0].date[:19]
            oldest = articles[-1].date[:19]
            logger.info(
                "Visible extract returned %d in-range articles (newest: %s, oldest: %s)",
                len(articles), newest, oldest,
            )
        else:
            logger.info("Visible extract returned 0 in-range articles.")

        return self._persist_articles(articles, context=context)

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
        extract_every_pages = max(0, int(self.args.extract_every_pages or 0))

        while True:
            # Check article limit
            element_count = len(
                self.driver.find_elements(
                    By.CSS_SELECTOR, config.SELECTORS["news_row"]
                )
            )
            if self.args.limit and not (self.args.start_date or self.args.end_date) and element_count >= self.args.limit:
                logger.info(
                    "Reached visible article limit (%d). Stopping load phase.",
                    self.args.limit,
                )
                break
            remaining = self._remaining_limit()
            if remaining == 0:
                logger.info(
                    "Reached persisted article limit (%d). Stopping load phase.",
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
                    if (!t) return null;
                    try { return new Date(t.getAttribute('datetime')).toISOString(); }
                    catch(e) { return t.getAttribute('datetime'); }
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

                # Periodic progress during loading — include oldest visible date
                if self.checkpoint.pages_loaded % 10 == 0:
                    oldest_vis = self.driver.execute_script("""
                        const rows = document.querySelectorAll('div.news-row.news-row-link');
                        if (rows.length === 0) return null;
                        const t = rows[rows.length - 1].querySelector('time');
                        if (!t) return null;
                        try { return new Date(t.getAttribute('datetime')).toISOString(); }
                        catch(e) { return t.getAttribute('datetime'); }
                    """)
                    logger.info(
                        "Pages loaded: %d, articles visible: %d, oldest visible: %s",
                        self.checkpoint.pages_loaded, element_count,
                        (oldest_vis or "N/A")[:19],
                    )
                if extract_every_pages and self.checkpoint.pages_loaded % extract_every_pages == 0:
                    self._extract_and_persist_visible_articles(
                        context=f"incremental checkpoint at page {self.checkpoint.pages_loaded}"
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
        new_count = self._extract_and_persist_visible_articles(context="final visible DOM pass")
        logger.info(
            "Extraction complete. %d new articles added (%d total).",
            new_count, len(self.checkpoint.articles),
        )
