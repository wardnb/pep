"""Daily Reddit researcher.

Keeps tabs on the latest community chatter about each vendor by querying
Reddit's public JSON search across the peptide subreddits. For every known
vendor it counts recent mentions, applies a light sentiment heuristic, and
records the newest post titles/links as fresh sources.

This runs on the app's daily scheduler (see scheduler.py). It does not overwrite
lab data — it only refreshes each vendor's community signal and attaches recent
discussion links, so the leaderboard reflects what people are saying *now*.

Reddit note: the public `.json` endpoints work for light, unauthenticated use
with a descriptive User-Agent. If Reddit rate-limits (HTTP 429), this scraper
logs and skips rather than failing the whole refresh. For heavier use, plug in
an OAuth token via the REDDIT_TOKEN env var.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from .base import BaseScraper, VendorRecord, register, utcnow_iso

try:
    import httpx
except ImportError:
    httpx = None

SUBREDDITS = ["Peptides", "PeptideCycles", "peptidesource"]

POSITIVE = ("legit", "tested", "great", "clean", "trusted", "passed", "recommend",
            "good to go", "g2g", "high purity", "solid")
NEGATIVE = ("scam", "fake", "underdosed", "under dosed", "bunk", "avoid", "failed",
            "sketchy", "ripoff", "rip off", "never received", "no coa")


def _sentiment(text: str) -> int:
    t = text.lower()
    return sum(t.count(w) for w in POSITIVE) - sum(t.count(w) for w in NEGATIVE)


@register
class RedditScraper(BaseScraper):
    name = "reddit"
    source_url = "https://www.reddit.com/r/Peptides"

    def __init__(self, *args, vendor_names: Optional[list[str]] = None,
                 days: int = 14, per_vendor_limit: int = 8, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor_names = vendor_names          # inject to control which vendors to poll
        self.days = days
        self.per_vendor_limit = per_vendor_limit

    def _known_vendor_names(self) -> list[str]:
        if self.vendor_names is not None:
            return self.vendor_names
        # Pull current vendor names from the DB so this stays in sync as vendors grow.
        try:
            from repository import list_vendors
            return [v["name"] for v in list_vendors()]
        except Exception as exc:  # noqa: BLE001
            print(f"[reddit] could not load vendor names: {exc}")
            return []

    def _search(self, vendor: str) -> list[dict]:
        if httpx is None:
            raise RuntimeError("httpx not installed")
        headers = {"User-Agent": "peptide-rater/1.0 (research; contact via app)"}
        token = os.environ.get("REDDIT_TOKEN")
        if token:
            headers["Authorization"] = f"bearer {token}"
        base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
        url = (f"{base}/r/{'+'.join(SUBREDDITS)}/search.json"
               f"?q={httpx.utils.quote(vendor)}&restrict_sr=1&sort=new&limit={self.per_vendor_limit}")
        try:
            resp = httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)
            if resp.status_code == 429:
                print(f"[reddit] rate-limited on '{vendor}', backing off")
                time.sleep(2)
                return []
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
            return [c["data"] for c in children]
        except Exception as exc:  # noqa: BLE001
            print(f"[reddit] search failed for '{vendor}': {exc}")
            return []

    def scrape(self) -> list[VendorRecord]:
        cutoff = time.time() - self.days * 86400 if httpx else 0
        records: list[VendorRecord] = []
        for vendor in self._known_vendor_names():
            posts = self._search(vendor)
            recent = [p for p in posts if p.get("created_utc", 0) >= cutoff] or posts
            if not recent:
                continue
            sent = sum(_sentiment(f"{p.get('title','')} {p.get('selftext','')}") for p in recent)
            # Map raw sentiment count to a bounded -1..+1 community score contribution.
            comm = max(-1.0, min(1.0, sent / 5.0))
            note = (f"{len(recent)} recent r/Peptides-network mentions "
                    f"(net sentiment {sent:+d}) as of {utcnow_iso()}")
            rec = VendorRecord(
                name=vendor,
                community_score=comm if sent != 0 else None,
                community_notes=note,
                sources=[{"title": f"r/{p.get('subreddit','Peptides')}: {p.get('title','')[:80]}",
                          "url": "https://www.reddit.com" + p.get("permalink", ""),
                          "retrieved_at": utcnow_iso()}
                         for p in recent[:5] if p.get("permalink")],
            )
            records.append(rec)
            time.sleep(0.5)  # be polite to Reddit
        print(f"[reddit] refreshed community signal for {len(records)} vendors")
        return records
