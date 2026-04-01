"""Retry decorator and URL resolution utilities."""

import functools
import html
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger("cryptopanic")

_BLOCK_TAG_RE = re.compile(
    r"(?is)<(script|style|noscript|svg|iframe|header|footer|nav|form)[^>]*>.*?</\1>"
)
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_COMMENT_RE = re.compile(r"(?is)<!--.*?-->")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_PARAGRAPH_BREAK_RE = re.compile(r"\n{3,}")
_ARTICLE_CONTAINER_PATTERNS = [
    re.compile(
        r'(?is)<(article|main|section|div)[^>]*?(?:itemprop=["\']articleBody["\']|class=["\'][^"\']*(?:article-body|entry-content|post-content|story-body|content-body|article__body|post-body|article-content|story-content)[^"\']*["\'])[^>]*>(.*?)</\1>'
    ),
    re.compile(r"(?is)<article\b[^>]*>(.*?)</article>"),
]
_PARAGRAPH_RE = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")


def retry(max_attempts=3, backoff_base=2, exceptions=(Exception,)):
    """Decorator: retry with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait = backoff_base ** attempt
                        logger.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %ds...",
                            attempt, max_attempts, func.__name__, e, wait,
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            max_attempts, func.__name__, e,
                        )
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator


def _is_cryptopanic_url(url: str) -> bool:
    """Check if a URL is still on cryptopanic.com (i.e. not resolved to publisher)."""
    from urllib.parse import urlparse
    return urlparse(url).hostname in (
        "cryptopanic.com", "www.cryptopanic.com", None,
    )


def resolve_single_url(cryptopanic_url: str, timeout: int = 10,
                       cookies: dict | None = None) -> str:
    """Follow CryptoPanic redirect to get the actual source URL.

    Returns the resolved publisher URL, or empty string if resolution fails
    or the URL still points to cryptopanic.com.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    resolved = ""
    try:
        resp = requests.head(
            cryptopanic_url, allow_redirects=True,
            timeout=timeout, cookies=cookies, headers=headers,
        )
        resolved = resp.url
    except requests.RequestException as e:
        logger.debug("HEAD failed for %s, trying GET: %s", cryptopanic_url, e)
        try:
            resp = requests.get(
                cryptopanic_url, allow_redirects=True,
                timeout=timeout, cookies=cookies, headers=headers, stream=True,
            )
            resolved = resp.url
            resp.close()
        except requests.RequestException as e2:
            logger.warning("URL resolution failed for %s: %s", cryptopanic_url, e2)
            return ""

    # CryptoPanic requires authentication for redirects to publisher URLs.
    # This is expected — not an error.
    if _is_cryptopanic_url(resolved):
        logger.debug(
            "URL stayed on CryptoPanic (auth required): %s",
            cryptopanic_url,
        )
        return ""
    return resolved


def resolve_urls_batch(url_map: dict, max_workers: int = 5,
                       timeout: int = 10, cookies: dict | None = None) -> dict:
    """Resolve multiple CryptoPanic redirect URLs in parallel.

    Args:
        url_map: {index: cryptopanic_url}

    Returns:
        {index: resolved_url}
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(resolve_single_url, url, timeout, cookies): idx
            for idx, url in url_map.items()
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.warning("URL resolution failed for article %s: %s", idx, e)
                results[idx] = ""
    return results


def _html_fragment_to_text(fragment: str) -> str:
    fragment = _COMMENT_RE.sub(" ", fragment or "")
    fragment = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?is)</(p|div|section|article|li|h[1-6])>", "\n", fragment)
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _PARAGRAPH_BREAK_RE.sub("\n\n", text)
    return text.strip()


def extract_article_content_from_html(page_html: str, max_chars: int = 20000) -> str:
    """Best-effort readable text extraction from article HTML."""
    if not page_html:
        return ""

    cleaned_html = _BLOCK_TAG_RE.sub(" ", page_html)
    candidates: list[str] = []

    for pattern in _ARTICLE_CONTAINER_PATTERNS:
        for match in pattern.finditer(cleaned_html):
            text = _html_fragment_to_text(match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1))
            if len(text) >= 80:
                candidates.append(text)

    paragraphs = [
        _html_fragment_to_text(match.group(1))
        for match in _PARAGRAPH_RE.finditer(cleaned_html)
    ]
    long_paragraphs = [p for p in paragraphs if len(p) >= 40]
    if long_paragraphs:
        candidates.append("\n\n".join(long_paragraphs[:80]))

    if not candidates:
        return ""

    best = max(candidates, key=len)
    if max_chars > 0:
        best = best[:max_chars].rstrip()
    return best


def download_article_content(url: str, timeout: int = 15, max_chars: int = 20000) -> str:
    """Fetch a publisher page and extract readable article text."""
    if not url:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Content download failed for %s: %s", url, e)
        return ""

    content_type = (resp.headers.get("content-type") or "").lower()
    if content_type and "html" not in content_type:
        logger.debug("Skipping non-HTML content at %s (%s)", url, content_type)
        return ""

    text = extract_article_content_from_html(resp.text, max_chars=max_chars)
    if not text:
        logger.debug("No readable article text extracted from %s", url)
    return text


def download_article_content_batch(url_map: dict, max_workers: int = 4,
                                   timeout: int = 15, max_chars: int = 20000) -> dict:
    """Download and extract article text for multiple URLs in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_article_content, url, timeout, max_chars): idx
            for idx, url in url_map.items()
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.warning("Content extraction failed for article %s: %s", idx, e)
                results[idx] = ""
    return results


def parse_vote_string(vote_str: str) -> tuple:
    """Parse vote title attribute like '45 bullish votes' -> ('bullish', 45)."""
    if not vote_str:
        return ("", 0)
    match = re.match(r"(\d+)\s*(.+?)(?:\s*votes?)?\s*$", vote_str.strip())
    if match:
        return (match.group(2).strip(), int(match.group(1)))
    return ("", 0)
