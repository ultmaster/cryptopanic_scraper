"""Tests for JSONLWriter."""

import json
import os
import tempfile

from cryptopanic_scraper.storage import JSONLWriter


def test_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31")
        writer.add({"title": "Article 1", "date": "2024-01-01"})
        writer.add({"title": "Article 2", "date": "2024-06-15"})
        writer.flush()

        with open(writer.filepath, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["title"] == "Article 1"
        assert json.loads(lines[1])["title"] == "Article 2"


def test_fresh_run_truncates():
    """A non-resume run should truncate existing file to avoid duplicates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer1 = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31")
        writer1.add({"title": "First"})
        writer1.flush()

        # Second writer without resume=True should start fresh
        writer2 = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31")
        assert writer2._total_written == 0
        writer2.add({"title": "Second"})
        writer2.flush()

        with open(writer2.filepath, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["title"] == "Second"


def test_resume_appends():
    """A resume run should append to existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer1 = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31")
        writer1.add({"title": "First"})
        writer1.flush()

        # Resume writer should keep existing data
        writer2 = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31", resume=True)
        assert writer2._total_written == 1
        writer2.add({"title": "Second"})
        writer2.flush()

        with open(writer2.filepath, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2


def test_total_written():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = JSONLWriter(tmpdir, "all", None, "2024-12-31")
        assert writer.total_written == 0
        writer.add({"title": "A"})
        assert writer.total_written == 1  # buffered but not flushed
        writer.flush()
        assert writer.total_written == 1
        writer.add({"title": "B"})
        writer.add({"title": "C"})
        assert writer.total_written == 3  # 1 flushed + 2 buffered


def test_finalize():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = JSONLWriter(tmpdir, "all", None, "2024-12-31")
        writer.add({"title": "Buffered"})
        writer.finalize()
        # finalize should flush the buffer
        with open(writer.filepath, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1


def test_filename_format():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = JSONLWriter(tmpdir, "hot", "2024-01-01", "2024-12-31")
        assert "cryptopanic_hot_all_2024-01-01_2024-12-31.jsonl" in writer.filepath

        writer2 = JSONLWriter(tmpdir, "all", None, "2024-12-31")
        assert "cryptopanic_all_all_all_2024-12-31.jsonl" in writer2.filepath

        writer3 = JSONLWriter(tmpdir, "all", "2024-01-01", "2024-12-31",
                              category="regulation")
        assert "cryptopanic_all_regulation_2024-01-01_2024-12-31.jsonl" in writer3.filepath
