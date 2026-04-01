"""Data models for scraped articles."""

from dataclasses import dataclass, field, asdict
import json


@dataclass
class Article:
    date: str                                    # ISO 8601 datetime string
    title: str
    currencies: list[str] = field(default_factory=list)
    votes: dict[str, int] = field(default_factory=dict)
    source_name: str = ""
    source_url: str = ""                         # Resolved external URL
    cryptopanic_url: str = ""                    # CryptoPanic redirect URL
    content_text: str = ""                       # Extracted article body text

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def dedup_key(self) -> str:
        """Unique key for deduplication (title + date)."""
        return f"{self.title}|{self.date}"
