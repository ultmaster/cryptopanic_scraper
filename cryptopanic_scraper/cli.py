"""Command-line argument parsing."""

import argparse
from datetime import date


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="CryptoPanic News Scraper — robust, resumable scraper with checkpointing."
    )

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity (DEBUG level logging)")
    parser.add_argument("-f", "--filter", default="all",
                        choices=["all", "hot", "rising", "bullish", "bearish",
                                 "lol", "commented", "important", "saved"],
                        help="News filter type (default: all)")
    parser.add_argument("-c", "--category", default=None,
                        choices=["price-analysis", "regulation", "media",
                                 "ico-news", "events"],
                        help="News category to scrape from (e.g. price-analysis, regulation)")
    parser.add_argument("-s", "--headless", action="store_true",
                        help="Run Chrome in headless mode")
    parser.add_argument("--manual-challenge-timeout", type=int, default=300,
                        help="When not headless, wait up to N seconds for you to solve a browser challenge (default: 300)")
    parser.add_argument("--debugger-address", type=str, default=None,
                        help="Attach Selenium to an already-running Chrome via host:port, e.g. 127.0.0.1:9222")
    parser.add_argument("--download-content", action="store_true",
                        help="Fetch and extract article body text from each resolved source URL")
    parser.add_argument("--content-max-chars", type=int, default=20000,
                        help="Maximum extracted characters to store per article (default: 20000)")
    parser.add_argument("--extract-every-pages", type=int, default=25,
                        help="During long scrolling runs, extract and persist visible articles every N loaded pages (default: 25)")
    parser.add_argument("-l", "--limit", type=int, default=None,
                        help="Maximum number of articles to scrape")

    # Date range
    parser.add_argument("--start-date", type=str, default=None,
                        help="Oldest article date to scrape (YYYY-MM-DD, e.g. 2016-01-01)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="Newest article date to scrape (YYYY-MM-DD, default: today)")

    # Output
    parser.add_argument("--output-dir", type=str, default="data",
                        help="Output directory (default: data)")

    # Checkpointing / resume
    parser.add_argument("--resume", action="store_true",
                        help="Resume from latest checkpoint")
    parser.add_argument("--checkpoint-interval", type=int, default=50,
                        help="Save checkpoint every N articles (default: 50)")

    # Logging
    parser.add_argument("--log-file", type=str, default="cryptopanic_scraper.log",
                        help="Log file path (default: cryptopanic_scraper.log)")

    # Retry
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max retries per operation (default: 3)")

    # URL resolution
    parser.add_argument("--no-resolve-urls", action="store_true",
                        help="Skip resolving source URLs (faster scraping)")

    args = parser.parse_args(argv)

    # Validate dates
    if args.start_date:
        _validate_date(parser, args.start_date, "--start-date")
    if args.end_date:
        _validate_date(parser, args.end_date, "--end-date")
    else:
        args.end_date = date.today().isoformat()

    return args


def _validate_date(parser, date_str, flag_name):
    try:
        date.fromisoformat(date_str)
    except ValueError:
        parser.error(f"{flag_name} must be YYYY-MM-DD format, got: {date_str}")
