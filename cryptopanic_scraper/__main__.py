"""Entry point for ``python -m cryptopanic_scraper``."""

from .cli import parse_args
from .logging_config import setup_logging
from .scraper import CryptoPanicScraper


def main():
    args = parse_args()
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file)
    logger.info("CryptoPanic Scraper starting...")
    logger.info(
        "Config: filter=%s, category=%s, start=%s, end=%s, limit=%s, headless=%s",
        args.filter, args.category, args.start_date, args.end_date, args.limit, args.headless,
    )

    scraper = CryptoPanicScraper(args)
    scraper.run()


if __name__ == "__main__":
    main()
