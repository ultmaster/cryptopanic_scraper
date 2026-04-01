"""Retry decorator and URL resolution utilities."""

import functools
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger("cryptopanic")


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

    # Validate that we actually left CryptoPanic
    if _is_cryptopanic_url(resolved):
        logger.warning(
            "URL resolved to CryptoPanic page, not publisher: %s -> %s",
            cryptopanic_url, resolved,
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


def parse_vote_string(vote_str: str) -> tuple:
    """Parse vote title attribute like '45 bullish votes' -> ('bullish', 45)."""
    if not vote_str:
        return ("", 0)
    match = re.match(r"(\d+)\s*(.+?)(?:\s*votes?)?\s*$", vote_str.strip())
    if match:
        return (match.group(2).strip(), int(match.group(1)))
    return ("", 0)
