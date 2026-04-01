"""Tests for CLI parsing."""

from cryptopanic_scraper.cli import parse_args


def test_manual_challenge_timeout_default():
    args = parse_args([])
    assert args.manual_challenge_timeout == 300


def test_manual_challenge_timeout_override():
    args = parse_args(["--manual-challenge-timeout", "45"])
    assert args.manual_challenge_timeout == 45


def test_debugger_address_override():
    args = parse_args(["--debugger-address", "127.0.0.1:9222"])
    assert args.debugger_address == "127.0.0.1:9222"


def test_download_content_args():
    args = parse_args([
        "--download-content",
        "--content-max-chars", "1234",
        "--extract-every-pages", "7",
    ])
    assert args.download_content is True
    assert args.content_max_chars == 1234
    assert args.extract_every_pages == 7


def test_category_default_is_none():
    args = parse_args([])
    assert args.category is None


def test_category_valid_choices():
    for cat in ["price-analysis", "regulation", "media", "ico-news", "events"]:
        args = parse_args(["--category", cat])
        assert args.category == cat


def test_category_short_flag():
    args = parse_args(["-c", "regulation"])
    assert args.category == "regulation"


def test_category_invalid_choice_exits(capsys):
    import pytest
    with pytest.raises(SystemExit):
        parse_args(["--category", "invalid-category"])
