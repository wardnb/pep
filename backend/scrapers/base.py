"""Base classes and registry for vendor-data scrapers.

Each scraper pulls public testing data from one source and returns a list of
normalised ``VendorRecord`` objects. The scheduler/ingest layer then upserts
those into the database and re-scores.

Scrapers are intentionally defensive: web pages change, so a scraper that fails
to parse should log and return an empty list rather than crash the whole run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    import httpx
except ImportError:  # keep import-time failures friendly
    httpx = None


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slugify(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name.strip()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


@dataclass
class VendorRecord:
    """Normalised vendor data returned by a scraper."""
    name: str
    website: Optional[str] = None
    publishes_coa: str = "unknown"
    community_score: Optional[float] = None
    community_notes: Optional[str] = None
    agg_score: Optional[float] = None
    agg_tests: Optional[int] = None
    agg_source_name: Optional[str] = None
    agg_source_url: Optional[str] = None
    notes: Optional[str] = None
    results: list[dict] = field(default_factory=list)   # test_result dicts
    sources: list[dict] = field(default_factory=list)   # {title, url, retrieved_at}

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_vendor_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "website": self.website,
            "publishes_coa": self.publishes_coa,
            "community_score": self.community_score,
            "community_notes": self.community_notes,
            "agg_score": self.agg_score,
            "agg_tests": self.agg_tests,
            "agg_source_name": self.agg_source_name,
            "agg_source_url": self.agg_source_url,
            "notes": self.notes,
        }


class BaseScraper:
    name = "base"
    source_url = ""

    def __init__(self, timeout: float = 20.0, user_agent: str = "peptide-rater/1.0"):
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, url: str) -> Optional[str]:
        if httpx is None:
            raise RuntimeError("httpx not installed; run `pip install httpx`")
        try:
            resp = httpx.get(url, timeout=self.timeout,
                             headers={"User-Agent": self.user_agent},
                             follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001 - defensive by design
            print(f"[{self.name}] fetch failed for {url}: {exc}")
            return None

    def scrape(self) -> list[VendorRecord]:
        """Override in subclasses. Return [] on failure, never raise."""
        raise NotImplementedError


# Registry so the CLI / scheduler can enumerate available scrapers by key.
_REGISTRY: dict[str, type[BaseScraper]] = {}


def register(cls: type[BaseScraper]) -> type[BaseScraper]:
    _REGISTRY[cls.name] = cls
    return cls


def get_scraper(name: str) -> BaseScraper:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown scraper '{name}'. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]()


def available_scrapers() -> list[str]:
    return list(_REGISTRY)
