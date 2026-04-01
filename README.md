


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
- **Date range scraping** -- specify `--start-date` and `--end-date` to target a specific time window (supports data back to Jan 2016)
- **Verbose logging** -- Python `logging` to both console and file; use `-v` for DEBUG output
- **Failure handling** -- per-article, page-level, and driver-level retries with exponential backoff; single article failures never crash the whole scrape
- **Network resilience** -- automatic WebDriver reconnection on crash (up to 5 attempts), checkpoint saved before every reconnect
- **Bulk extraction** -- articles are extracted from the DOM in a single JavaScript call, avoiding stale element issues
- **Parallel URL resolution** -- source URLs are resolved via `requests` in a thread pool, independent of Selenium
- **JSONL output** -- one JSON object per line, append-friendly and incremental

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

Limit the number of articles:
```sh
python -m cryptopanic_scraper --limit 100 --headless
```

Skip source URL resolution for faster scraping:
```sh
python -m cryptopanic_scraper --limit 100 --headless --no-resolve-urls
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

### Checkpointing and Resume

The scraper automatically saves checkpoints to `data/checkpoints/`. Checkpoints are saved:
- Every 50 articles (configurable with `--checkpoint-interval`)
- Every 50 "Load More" page clicks
- On Ctrl+C (SIGINT) or SIGTERM

If a scrape is interrupted, resume it:
```sh
python -m cryptopanic_scraper --start-date 2016-01-01 --headless --resume
```

### All Options

```
usage: __main__.py [-h] [-v]
                   [-f {all,hot,rising,bullish,bearish,lol,commented,important,saved}]
                   [-s] [-l LIMIT] [--start-date START_DATE]
                   [--end-date END_DATE] [--output-dir OUTPUT_DIR] [--resume]
                   [--checkpoint-interval CHECKPOINT_INTERVAL]
                   [--log-file LOG_FILE] [--max-retries MAX_RETRIES]
                   [--no-resolve-urls]

options:
  -h, --help            show this help message and exit
  -v, --verbose         Increase output verbosity (DEBUG level logging)
  -f, --filter          News filter type (default: all)
  -s, --headless        Run Chrome in headless mode
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
data/cryptopanic_all_2016-01-01_2026-04-01.jsonl
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
  "cryptopanic_url": "https://cryptopanic.com/news/12345/click/"
}
```

## Testing

Run the test suite:
```sh
python -m pytest tests/ -v
```

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