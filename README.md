


<!-- PROJECT SHIELDS -->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]



<!-- PROJECT LOGO -->
<br />
<p align="center">
  <a href="https://github.com/grilledchickenthighs/cryptopanic_scraper">
    <img src="images/logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">Cryptopanic Scraper</h3>

  <p align="center">
    Robust, resumable Selenium scraper for CryptoPanic's news feed with checkpointing, date range support, and JSONL output.
    <br />
    <a href="#usage"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/grilledchickenthighs/cryptopanic_scraper/issues">Report Bug</a>
    ·
    <a href="https://github.com/grilledchickenthighs/cryptopanic_scraper/issues">Request Feature</a>
  </p>
</p>



<!-- TABLE OF CONTENTS -->
## Table of Contents

* [About the Project](#about-the-project)
  * [Features](#features)
  * [Built With](#built-with)
* [Getting Started](#getting-started)
  * [Prerequisites](#prerequisites)
  * [Installation](#installation)
* [Usage](#usage)
  * [Basic Usage](#basic-usage)
  * [Date Range Scraping](#date-range-scraping)
  * [Checkpointing and Resume](#checkpointing-and-resume)
  * [Cloudflare Challenges](#cloudflare-challenges)
  * [All Options](#all-options)
* [Project Structure](#project-structure)
* [Output Format](#output-format)
* [Testing](#testing)
* [Roadmap](#roadmap)
* [Contributing](#contributing)
* [License](#license)
* [Contact](#contact)



<!-- ABOUT THE PROJECT -->
## About The Project

[![Product Name Screen Shot][product-screenshot]](https://cryptopanic.com/)

Cryptopanic is a crypto news aggregator that offers realtime news feeds of all things crypto as well 
as user input for ratings.
This project was designed to scrape the data from their website so it could be later analyzed using NLP.

### Features

- **Checkpointing** -- saves progress periodically and on Ctrl+C; resume any interrupted scrape with `--resume`
- **Category support** -- scrape specific news categories: `price-analysis`, `regulation`, `media`, `ico-news`, `events`
- **Date range scraping** -- specify `--start-date` and `--end-date` to target a specific time window (supports data back to Jan 2016)
- **Verbose logging** -- Python `logging` to both console and file; use `-v` for DEBUG output
- **Failure handling** -- per-article, page-level, and driver-level retries with exponential backoff; single article failures never crash the whole scrape
- **Network resilience** -- automatic WebDriver reconnection on crash (up to 5 attempts), checkpoint saved before every reconnect
- **Bulk extraction** -- articles are extracted from the DOM in a single JavaScript call, avoiding stale element issues
- **Parallel URL resolution** -- source URLs are resolved via `requests` in a thread pool, independent of Selenium
- **Optional content download** -- fetch and extract readable article body text from each resolved source URL
- **JSONL output** -- one JSON object per line, append-friendly and incremental
- **Manual browser attach** -- optionally connect Selenium to an already-running Chrome session so you can clear site challenges before scraping
- **Incremental backfills** -- long historical runs can extract and persist matches every N pages instead of waiting for one final DOM dump

### Built With

* [Python 3](https://github.com/topics/python)
* [Selenium 4](https://github.com/topics/selenium)
* [Requests](https://docs.python-requests.org/)



<!-- GETTING STARTED -->
## Getting Started

To get a local copy up and running follow these simple steps.

### Prerequisites

* Python 3.10+
* pip
* Google Chrome (or Chromium) installed

### Installation
 
1. Clone the repository
    ```sh
    git clone https://github.com/grilledchickenthighs/cryptopanic_scraper.git
    ```
2. Change directory
    ```sh
    cd cryptopanic_scraper
    ```
3. Install packages
    ```sh
    pip install -r requirements.txt
    ```



<!-- USAGE EXAMPLES -->
## Usage

### Basic Usage

Run headless with verbose logging:
```sh
python -m cryptopanic_scraper --headless -v
```

Watch it in action (opens a browser window):
```sh
python -m cryptopanic_scraper
```

Filter by news type:
```sh
python -m cryptopanic_scraper --filter hot --headless
```

### Category Scraping

Scrape a specific news category instead of the full feed:
```sh
# Price analysis articles
python -m cryptopanic_scraper --category price-analysis --headless

# Regulation news
python -m cryptopanic_scraper --category regulation --headless

# Media / video content
python -m cryptopanic_scraper --category media --headless

# ICO and fundraising news
python -m cryptopanic_scraper --category ico-news --headless

# Events
python -m cryptopanic_scraper --category events --headless
```

Combine category with a filter:
```sh
python -m cryptopanic_scraper --category regulation --filter hot --headless
```

Limit the number of articles:
```sh
python -m cryptopanic_scraper --limit 100 --headless
```

Skip source URL resolution for faster scraping:
```sh
python -m cryptopanic_scraper --limit 100 --headless --no-resolve-urls
```

Download readable article body text into the JSONL:
```sh
python -m cryptopanic_scraper --limit 100 --download-content
```

If you expect to solve a site challenge manually, keep the browser open and wait for up to 5 minutes:
```sh
python -m cryptopanic_scraper --limit 100 --manual-challenge-timeout 300
```

You can also use the root convenience script:
```sh
python run_scraper.py --headless -v
```

### Date Range Scraping

Scrape articles from a specific date range:
```sh
python -m cryptopanic_scraper --start-date 2024-01-01 --end-date 2024-12-31 --headless
```

Scrape all the way back to 2016:
```sh
python -m cryptopanic_scraper --start-date 2016-01-01 --headless
```

Backfill a historical window such as calendar year 2016:
```sh
python -m cryptopanic_scraper --start-date 2016-01-01 --end-date 2016-12-31 --resume
```

For long historical runs, the scraper now re-extracts and persists visible in-range rows every `--extract-every-pages` pages. That makes deep backfills safer to interrupt and resume:
```sh
python -m cryptopanic_scraper --start-date 2016-01-01 --end-date 2016-12-31 --extract-every-pages 10 --resume
```

### Checkpointing and Resume

The scraper automatically saves checkpoints to `data/checkpoints/`. Checkpoints are saved:
- Every 50 articles (configurable with `--checkpoint-interval`)
- Every 50 "Load More" page clicks
- On Ctrl+C (SIGINT) or SIGTERM

If a scrape is interrupted, resume it:
```sh
python -m cryptopanic_scraper --start-date 2016-01-01 --headless --resume
```

### Cloudflare Challenges

CryptoPanic may occasionally return a Cloudflare interstitial page instead of the news feed. When that happens:

- `--headless` runs will fail immediately with a clear error explaining that the browser hit a blocking page
- non-headless runs will keep Chrome open and wait up to `--manual-challenge-timeout` seconds for you to solve the challenge manually

If the challenge keeps looping in Selenium-controlled Chrome, use a normal Chrome session first and then attach the scraper to it.

1. Launch Chrome with remote debugging enabled:
   ```sh
   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/cryptopanic-debug-profile 'https://www.cryptopanic.com/news?filter=all'
   ```
2. Complete the challenge in that Chrome window until the actual CryptoPanic feed is visible.
3. Attach the scraper to the same session:
   ```sh
   python -m cryptopanic_scraper --limit 100 --debugger-address 127.0.0.1:9222
   ```

This attach flow reuses your existing browser session instead of launching a fresh Selenium-controlled profile.

### Content Download Notes

When `--download-content` is enabled, the scraper:

- resolves the CryptoPanic redirect to the publisher URL
- downloads the publisher HTML with `requests`
- extracts a best-effort readable text body and stores it as `content_text` in the JSONL

This is intentionally heuristic. Some publishers will return clean article text, while others may block requests or render content dynamically and produce an empty `content_text`.

### All Options

```
usage: __main__.py [-h] [-v]
                   [-f {all,hot,rising,bullish,bearish,lol,commented,important,saved}]
                   [-c {price-analysis,regulation,media,ico-news,events}]
                   [-s] [--manual-challenge-timeout MANUAL_CHALLENGE_TIMEOUT]
                   [--debugger-address DEBUGGER_ADDRESS] [--download-content]
                   [--content-max-chars CONTENT_MAX_CHARS]
                   [--extract-every-pages EXTRACT_EVERY_PAGES] [-l LIMIT] [--start-date START_DATE]
                   [--end-date END_DATE] [--output-dir OUTPUT_DIR] [--resume]
                   [--checkpoint-interval CHECKPOINT_INTERVAL]
                   [--log-file LOG_FILE] [--max-retries MAX_RETRIES]
                   [--no-resolve-urls]

options:
  -h, --help            show this help message and exit
  -v, --verbose         Increase output verbosity (DEBUG level logging)
  -f, --filter          News filter type (default: all)
  -c, --category        News category to scrape from (e.g. price-analysis,
                        regulation, media, ico-news, events)
  -s, --headless        Run Chrome in headless mode
  --manual-challenge-timeout
                        When not headless, wait up to N seconds for you to
                        solve a browser challenge (default: 300)
  --debugger-address    Attach Selenium to an already-running Chrome via
                        host:port, e.g. 127.0.0.1:9222
  --download-content    Fetch and extract article body text from each
                        resolved source URL
  --content-max-chars   Maximum extracted characters to store per article
                        (default: 20000)
  --extract-every-pages
                        During long scrolling runs, extract and persist
                        visible articles every N loaded pages (default: 25)
  -l, --limit           Maximum number of articles to scrape
  --start-date          Oldest article date (YYYY-MM-DD, e.g. 2016-01-01)
  --end-date            Newest article date (YYYY-MM-DD, default: today)
  --output-dir          Output directory (default: data)
  --resume              Resume from latest checkpoint
  --checkpoint-interval Save checkpoint every N articles (default: 50)
  --log-file            Log file path (default: cryptopanic_scraper.log)
  --max-retries         Max retries per operation (default: 3)
  --no-resolve-urls     Skip resolving source URLs (faster scraping)
```

<!-- PROJECT STRUCTURE -->
## Project Structure

```
cryptopanic_scraper/
    __init__.py           # Package init
    __main__.py           # Entry point (python -m cryptopanic_scraper)
    cli.py                # Argument parsing
    config.py             # Constants, CSS selectors, JS scripts
    scraper.py            # CryptoPanicScraper class (core logic)
    models.py             # Article dataclass
    checkpoint.py         # Save/load/resume checkpoint state
    storage.py            # JSONL output writer
    utils.py              # Retry decorator, URL resolution
    logging_config.py     # Logging setup
run_scraper.py            # Convenience entry script
tests/                    # Unit tests
```

## Output Format

Output is saved as JSONL (one JSON object per line) in the `data/` directory:

```
data/cryptopanic_all_all_2016-01-01_2026-04-01.jsonl          # no category
data/cryptopanic_all_regulation_2016-01-01_2026-04-01.jsonl   # with --category regulation
```

Each line contains:
```json
{
  "date": "2025-03-15T10:30:00Z",
  "title": "Bitcoin hits new milestone",
  "currencies": ["BTC", "ETH"],
  "votes": {"bullish": 45, "bearish": 3},
  "source_name": "CoinDesk",
  "source_url": "https://coindesk.com/article/...",
  "cryptopanic_url": "https://cryptopanic.com/news/12345/click/",
  "content_text": "Bitcoin climbed above ..."
}
```

## Testing

Run the unit test suite:
```sh
python -m pytest tests/ -v --ignore=tests/test_category_integration.py
```

Run the integration tests (requires Chrome running with remote debugging on port 9222):
```sh
# 1. Launch Chrome with remote debugging:
google-chrome --remote-debugging-port=9222 \
    --user-data-dir=/tmp/cryptopanic-debug-profile \
    'https://www.cryptopanic.com/news'

# 2. Run integration tests:
python -m pytest tests/test_category_integration.py -v
```

The integration tests connect to Chrome on port 9222 and verify that each news category (`price-analysis`, `regulation`, `media`, `ico-news`, `events`) loads correctly and the JS extraction script works.

If you're interested in analyzing the data, check out the [jupyter](https://github.com/GrilledChickenThighs/cryptopanic_scraper/tree/master/jupyter) directory for getting started.

<!-- ROADMAP -->
## Roadmap

See the [open issues](https://github.com/grilledchickenthighs/cryptopanic_scraper/issues) for a list of proposed features (and known issues).



<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request



<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE` for more information.



<!-- CONTACT -->
## Contact

[Paul Mendes](https://grilledchickenthighs.github.io/) - [@BTCTradeNation](https://twitter.com/BTCTradeNation) - [paulsperformance@gmail.com](mailto:paulseperformance@gmail.com)

Project Link: [https://github.com/grilledchickenthighs/cryptopanic_scraper](https://github.com/grilledchickenthighs/cryptopanic_scraper)



<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/grilledchickenthighs/cryptopanic_scraper?style=flat-square
[contributors-url]: https://github.com/GrilledChickenThighs/cryptopanic_scraper/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/grilledchickenthighs/cryptopanic_scraper?style=flat-sqaure
[forks-url]: https://github.com/GrilledChickenThighs/cryptopanic_scraper/network/members
[stars-shield]: https://img.shields.io/github/stars/grilledchickenthighs/cryptopanic_scraper?style=flat-square
[stars-url]: https://github.com/grilledchickenthighs/cryptopanic_scraper/stargazers
[issues-shield]: https://img.shields.io/github/issues/grilledchickenthighs/cryptopanic_scraper.svg?style=flat-square
[issues-url]: https://github.com/grilledchickenthighs/cryptopanic_scraper/issues
[license-shield]: https://img.shields.io/github/license/grilledchickenthighs/cryptopanic_scraper.svg?style=flat-square
[license-url]: https://github.com/grilledchickenthighs/cryptopanic_scraper/blob/master/LICENSE.txt
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=flat-square&logo=linkedin&colorB=555
[linkedin-url]: https://linkedin.com/in/paul-mendes
[product-screenshot]: images/screenshot.png
