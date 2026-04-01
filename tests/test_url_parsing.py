"""Tests for URL parsing and vote string parsing utilities."""

from unittest.mock import patch, MagicMock

from cryptopanic_scraper.utils import parse_vote_string, resolve_single_url, _is_cryptopanic_url


def test_parse_vote_string_standard():
    assert parse_vote_string("45 bullish votes") == ("bullish", 45)


def test_parse_vote_string_single_vote():
    assert parse_vote_string("1 bearish vote") == ("bearish", 1)


def test_parse_vote_string_no_votes_suffix():
    assert parse_vote_string("12 lol") == ("lol", 12)


def test_parse_vote_string_empty():
    assert parse_vote_string("") == ("", 0)


def test_parse_vote_string_none():
    assert parse_vote_string(None) == ("", 0)


def test_parse_vote_string_malformed():
    assert parse_vote_string("no numbers here") == ("", 0)


def test_resolve_single_url_success():
    mock_response = MagicMock()
    mock_response.url = "https://coindesk.com/real-article"
    with patch("cryptopanic_scraper.utils.requests.head", return_value=mock_response):
        result = resolve_single_url("https://cryptopanic.com/news/123/click/")
        assert result == "https://coindesk.com/real-article"


def test_resolve_single_url_head_fails_get_succeeds():
    mock_get_response = MagicMock()
    mock_get_response.url = "https://coindesk.com/fallback"

    import requests
    with patch("cryptopanic_scraper.utils.requests.head", side_effect=requests.RequestException("timeout")):
        with patch("cryptopanic_scraper.utils.requests.get", return_value=mock_get_response):
            result = resolve_single_url("https://cryptopanic.com/news/123/click/")
            assert result == "https://coindesk.com/fallback"


def test_resolve_single_url_both_fail():
    import requests
    with patch("cryptopanic_scraper.utils.requests.head", side_effect=requests.RequestException("fail")):
        with patch("cryptopanic_scraper.utils.requests.get", side_effect=requests.RequestException("fail")):
            result = resolve_single_url("https://cryptopanic.com/news/123/click/")
            assert result == ""


def test_resolve_single_url_rejects_cryptopanic_url():
    """If the redirect stays on cryptopanic.com, return empty string."""
    mock_response = MagicMock()
    mock_response.url = "https://cryptopanic.com/news/12345/"
    with patch("cryptopanic_scraper.utils.requests.head", return_value=mock_response):
        result = resolve_single_url("https://cryptopanic.com/news/12345/click/")
        assert result == ""


def test_is_cryptopanic_url():
    assert _is_cryptopanic_url("https://cryptopanic.com/news/123/") is True
    assert _is_cryptopanic_url("https://www.cryptopanic.com/foo") is True
    assert _is_cryptopanic_url("https://coindesk.com/article") is False
    assert _is_cryptopanic_url("") is True  # no hostname = invalid
