"""Tests for article content extraction helpers."""

from unittest.mock import MagicMock, patch

from cryptopanic_scraper.utils import (
    download_article_content,
    download_article_content_batch,
    extract_article_content_from_html,
)


def test_extract_article_content_from_article_tag():
    html = """
    <html><body>
      <article>
        <h1>Headline</h1>
        <p>This is the first paragraph with enough detail to count as article text.</p>
        <p>This is the second paragraph with more than enough words to be useful.</p>
        <script>ignored()</script>
      </article>
    </body></html>
    """
    text = extract_article_content_from_html(html)
    assert "Headline" in text
    assert "first paragraph" in text
    assert "ignored()" not in text


def test_extract_article_content_falls_back_to_paragraphs():
    html = """
    <html><body>
      <div><p>Short.</p></div>
      <div><p>This fallback paragraph is long enough to be included in the extracted content output.</p></div>
      <div><p>This is another paragraph that should appear in the combined readable text.</p></div>
    </body></html>
    """
    text = extract_article_content_from_html(html)
    assert "fallback paragraph" in text
    assert "another paragraph" in text


def test_download_article_content_success():
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.text = """
    <html><body><article><p>This is a readable article body with enough length to extract successfully.</p></article></body></html>
    """
    mock_response.raise_for_status.return_value = None
    with patch("cryptopanic_scraper.utils.requests.get", return_value=mock_response):
        text = download_article_content("https://example.com/news")
    assert "readable article body" in text


def test_download_article_content_batch():
    with patch("cryptopanic_scraper.utils.download_article_content") as mock_download:
        mock_download.side_effect = ["first body", "second body"]
        result = download_article_content_batch({
            0: "https://example.com/1",
            1: "https://example.com/2",
        }, max_workers=2)
    assert result[0] == "first body"
    assert result[1] == "second body"
