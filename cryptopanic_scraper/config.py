"""All constants, CSS selectors, and defaults in one place."""

# CSS Selectors — single source of truth. If CryptoPanic changes their DOM, update here only.
SELECTORS = {
    "news_row": "div.news-row.news-row-link",
    "load_more": "btn-outline-primary",
    "time": "time",
    "title": "span.title-text span:first-child",
    "title_parent": "span.title-text",
    "currencies": ".colored-link",
    "votes": "span.nc-vote-cont",
    "article_link": "a.news-cell.nc-title",
    "source_name": "span.si-source-name",
}

# Timing
SCROLL_PAUSE = 1.0
PAGE_LOAD_TIMEOUT = 15
LOAD_MORE_GRACE_TIMEOUT = 20
LOAD_MORE_POLL_INTERVAL = 0.5
BATCH_DELAY = 0.5

# Retry
MAX_ARTICLE_RETRIES = 3
MAX_PAGE_RETRIES = 3
MAX_DRIVER_RECONNECTS = 5
RETRY_BACKOFF_BASE = 2

# URL Resolution
URL_RESOLVE_WORKERS = 5
URL_RESOLVE_TIMEOUT = 10

# Content extraction
CONTENT_FETCH_WORKERS = 4
CONTENT_FETCH_TIMEOUT = 15
DEFAULT_CONTENT_MAX_CHARS = 20000

# Incremental extraction during long backfills
DEFAULT_EXTRACT_EVERY_PAGES = 25

# Checkpointing
DEFAULT_CHECKPOINT_INTERVAL = 50
CHECKPOINT_DIR = "data/checkpoints"

# Output
DEFAULT_OUTPUT_DIR = "data"
BASE_URL = "https://www.cryptopanic.com/news"

# Bulk JS extraction script — extracts all visible articles from the DOM in one call.
# Returns a list of plain objects, avoiding any stale-element issues.
EXTRACT_ARTICLES_JS = """
return Array.from(document.querySelectorAll('div.news-row.news-row-link')).map((el, idx) => {
    const timeEl = el.querySelector('time');
    const rawDate = timeEl ? timeEl.getAttribute('datetime') : null;
    // Normalize to ISO 8601 — the attribute may be a locale string, not ISO
    let datetime = null;
    if (rawDate) {
        try { datetime = new Date(rawDate).toISOString(); } catch(e) { datetime = rawDate; }
    }

    const titleEl = el.querySelector('span.title-text span:first-child');
    const title = titleEl ? titleEl.textContent.trim() : '';

    const linkEl = el.querySelector('a.news-cell.nc-title');
    const href = linkEl ? linkEl.href : '';

    const sourceEl = el.querySelector('span.si-source-name');
    const source = sourceEl ? sourceEl.textContent.trim() : '';

    const currencies = Array.from(el.querySelectorAll('.colored-link'))
        .map(c => c.textContent.trim());

    const votes = {};
    el.querySelectorAll('span.nc-vote-cont').forEach(v => {
        const t = v.getAttribute('title');
        if (t) {
            const match = t.match(/^(\\d+)\\s*(.+?)(?:\\s*votes?)?\\s*$/);
            if (match) {
                votes[match[2].trim()] = parseInt(match[1]);
            }
        }
    });

    return { idx, datetime, title, href, source, currencies, votes };
});
"""
