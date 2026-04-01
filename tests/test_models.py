"""Tests for Article data model."""

from cryptopanic_scraper.models import Article


def test_to_dict_roundtrip():
    article = Article(
        date="2025-03-15T10:30:00Z",
        title="Bitcoin hits new high",
        currencies=["BTC", "ETH"],
        votes={"bullish": 45, "bearish": 3},
        source_name="CoinDesk",
        source_url="https://coindesk.com/article",
        cryptopanic_url="https://cryptopanic.com/news/12345/click/",
    )
    d = article.to_dict()
    restored = Article.from_dict(d)
    assert restored == article


def test_from_dict_ignores_extra_keys():
    d = {
        "date": "2025-01-01T00:00:00Z",
        "title": "Test",
        "extra_field": "should be ignored",
    }
    article = Article.from_dict(d)
    assert article.title == "Test"
    assert article.date == "2025-01-01T00:00:00Z"
    assert article.currencies == []
    assert article.votes == {}


def test_dedup_key():
    a1 = Article(date="2025-03-15T10:30:00Z", title="Same Title")
    a2 = Article(date="2025-03-15T10:30:00Z", title="Same Title")
    a3 = Article(date="2025-03-15T10:30:00Z", title="Different Title")
    assert a1.dedup_key == a2.dedup_key
    assert a1.dedup_key != a3.dedup_key


def test_to_json():
    article = Article(date="2025-01-01T00:00:00Z", title="Test Article")
    json_str = article.to_json()
    assert '"date": "2025-01-01T00:00:00Z"' in json_str
    assert '"title": "Test Article"' in json_str


def test_defaults():
    article = Article(date="2025-01-01T00:00:00Z", title="Minimal")
    assert article.currencies == []
    assert article.votes == {}
    assert article.source_name == ""
    assert article.source_url == ""
    assert article.cryptopanic_url == ""
