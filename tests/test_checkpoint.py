"""Tests for CheckpointManager."""

import os
import tempfile

from cryptopanic_scraper.checkpoint import CheckpointManager


def _make_manager(tmpdir, interval=50):
    return CheckpointManager(
        filter_type="all",
        start_date="2024-01-01",
        end_date="2024-12-31",
        checkpoint_dir=tmpdir,
        interval=interval,
    )


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir)
        mgr.add_article({"title": "Article 1", "date": "2024-06-15T00:00:00Z"})
        mgr.add_article({"title": "Article 2", "date": "2024-07-20T00:00:00Z"})
        mgr.pages_loaded = 5
        mgr.save()

        mgr2 = _make_manager(tmpdir)
        assert mgr2.load() is True
        assert len(mgr2.articles) == 2
        assert mgr2.pages_loaded == 5
        assert mgr2.oldest_date == "2024-06-15T00:00:00Z"
        assert mgr2.newest_date == "2024-07-20T00:00:00Z"


def test_deduplication():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir)
        assert mgr.add_article({"title": "A", "date": "2024-01-01T00:00:00Z"}) is True
        assert mgr.add_article({"title": "A", "date": "2024-01-01T00:00:00Z"}) is False
        assert len(mgr.articles) == 1


def test_auto_save_at_interval():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir, interval=3)
        mgr.add_article({"title": "A", "date": "2024-01-01T00:00:00Z"})
        mgr.add_article({"title": "B", "date": "2024-01-02T00:00:00Z"})
        assert not os.path.exists(mgr.checkpoint_path)
        mgr.add_article({"title": "C", "date": "2024-01-03T00:00:00Z"})
        # Interval of 3 reached — checkpoint should be auto-saved
        assert os.path.exists(mgr.checkpoint_path)


def test_load_nonexistent_returns_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir)
        assert mgr.load() is False


def test_date_tracking():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir)
        mgr.add_article({"title": "Mid", "date": "2024-06-15T00:00:00Z"})
        mgr.add_article({"title": "Early", "date": "2024-01-01T00:00:00Z"})
        mgr.add_article({"title": "Late", "date": "2024-12-31T00:00:00Z"})
        assert mgr.oldest_date == "2024-01-01T00:00:00Z"
        assert mgr.newest_date == "2024-12-31T00:00:00Z"


def test_failed_articles():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = _make_manager(tmpdir)
        mgr.add_failed({"error": "timeout", "title": "Bad Article"})
        mgr.save()

        mgr2 = _make_manager(tmpdir)
        mgr2.load()
        assert len(mgr2.failed_articles) == 1
        assert mgr2.failed_articles[0]["error"] == "timeout"
