"""JSONL output writer with incremental append."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("cryptopanic")


class JSONLWriter:
    def __init__(self, output_dir: str, filter_type: str,
                 start_date: str | None, end_date: str,
                 resume: bool = False):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filename = f"cryptopanic_{filter_type}_{start_date or 'all'}_{end_date}.jsonl"
        self.filepath = os.path.join(output_dir, filename)
        self._buffer: list[dict] = []
        self._total_written: int = 0

        if os.path.exists(self.filepath):
            if resume:
                # Count existing lines to continue from where we left off
                with open(self.filepath, "r") as f:
                    self._total_written = sum(1 for _ in f)
                logger.info(
                    "Resuming — appending to existing file with %d articles: %s",
                    self._total_written, self.filepath,
                )
            else:
                # Fresh run — truncate the file to avoid duplicates
                open(self.filepath, "w").close()
                logger.info("Starting fresh — cleared existing file: %s", self.filepath)

    def add(self, article_dict: dict):
        """Buffer an article for writing."""
        self._buffer.append(article_dict)

    def flush(self):
        """Write buffered articles to disk."""
        if not self._buffer:
            return
        with open(self.filepath, "a", encoding="utf-8") as f:
            for article in self._buffer:
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
        count = len(self._buffer)
        self._total_written += count
        self._buffer.clear()
        logger.debug(
            "Flushed %d articles to %s (total: %d)",
            count, self.filepath, self._total_written,
        )

    @property
    def total_written(self) -> int:
        return self._total_written + len(self._buffer)

    def finalize(self):
        """Final flush and log summary."""
        self.flush()
        logger.info(
            "Output complete: %d articles written to %s",
            self._total_written, self.filepath,
        )
