"""Checkpoint management for resumable scraping."""

import json
import logging
import os
import signal
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("cryptopanic")


class CheckpointManager:
    def __init__(self, filter_type: str, start_date: str | None,
                 end_date: str, checkpoint_dir: str = "data/checkpoints",
                 interval: int = 50, category: str | None = None):
        self.filter_type = filter_type
        self.category = category or "all"
        self.start_date = start_date or "none"
        self.end_date = end_date
        self.checkpoint_dir = checkpoint_dir
        self.interval = interval

        self.articles: list[dict] = []
        self.seen_keys: set[str] = set()
        self.pages_loaded: int = 0
        self.oldest_date: str | None = None
        self.newest_date: str | None = None
        self.failed_articles: list[dict] = []
        self.articles_since_save: int = 0

        Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)

    @property
    def checkpoint_path(self) -> str:
        return os.path.join(
            self.checkpoint_dir,
            f"checkpoint_{self.filter_type}_{self.category}_{self.start_date}_{self.end_date}.json",
        )

    def add_article(self, article_dict: dict) -> bool:
        """Add article if not a duplicate. Returns True if added."""
        key = f"{article_dict.get('title', '')}|{article_dict.get('date', '')}"
        if key in self.seen_keys:
            logger.debug("Skipping duplicate: %s", article_dict.get("title", "")[:50])
            return False
        self.seen_keys.add(key)
        self.articles.append(self._compact_article(article_dict))
        self.articles_since_save += 1

        # Track date range
        article_date = article_dict.get("date", "")
        if article_date:
            if self.oldest_date is None or article_date < self.oldest_date:
                self.oldest_date = article_date
            if self.newest_date is None or article_date > self.newest_date:
                self.newest_date = article_date

        # Auto-save at interval
        if self.articles_since_save >= self.interval:
            self.save()
        return True

    def _compact_article(self, article_dict: dict) -> dict:
        """Keep checkpoints resumable without storing large article bodies."""
        compact = dict(article_dict)
        content_text = compact.get("content_text", "")
        if content_text:
            compact["content_text"] = ""
            compact["content_length"] = len(content_text)
        return compact

    def add_failed(self, info: dict):
        """Record a failed article extraction."""
        self.failed_articles.append(info)

    def increment_pages(self):
        self.pages_loaded += 1

    def save(self):
        """Save checkpoint to disk (atomic write via temp + rename)."""
        data = {
            "filter_type": self.filter_type,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "pages_loaded": self.pages_loaded,
            "oldest_date": self.oldest_date,
            "newest_date": self.newest_date,
            "total_articles": len(self.articles),
            "total_failed": len(self.failed_articles),
            "seen_keys": list(self.seen_keys),
            "articles": self.articles,
            "failed_articles": self.failed_articles,
            "saved_at": datetime.now().isoformat(),
        }
        tmp_path = self.checkpoint_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, self.checkpoint_path)
        self.articles_since_save = 0
        logger.info(
            "Checkpoint saved: %d articles, pages=%d, oldest=%s",
            len(self.articles), self.pages_loaded, self.oldest_date,
        )

    def load(self) -> bool:
        """Load checkpoint from disk. Returns True if loaded successfully."""
        if not os.path.exists(self.checkpoint_path):
            logger.info("No checkpoint found, starting fresh.")
            return False
        with open(self.checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.articles = data.get("articles", [])
        self.seen_keys = set(data.get("seen_keys", []))
        self.pages_loaded = data.get("pages_loaded", 0)
        self.oldest_date = data.get("oldest_date")
        self.newest_date = data.get("newest_date")
        self.failed_articles = data.get("failed_articles", [])
        logger.info(
            "Checkpoint loaded: %d articles, pages=%d, oldest=%s",
            len(self.articles), self.pages_loaded, self.oldest_date,
        )
        return True

    def register_signal_handlers(self):
        """Register SIGINT/SIGTERM handlers to save checkpoint before exit."""
        def handler(signum, _frame):
            sig_name = signal.Signals(signum).name
            logger.warning("Received %s — saving checkpoint before exit...", sig_name)
            self.save()
            logger.info("Checkpoint saved. Exiting.")
            raise SystemExit(0)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
