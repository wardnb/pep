"""Scraper for Peptigrity (peptigrity.com/lab-tests) — aggregates individual
third-party lab results and publishes an auto-recalculated per-vendor trust
score (HPLC purity weighted ~60%), excluding in-house vendor testing.

Like the Finnrick scraper, this reads only the public listing. Selectors are
best-effort and documented so they are easy to fix if the markup changes.
"""
from __future__ import annotations

import re
from typing import Optional

from .base import BaseScraper, VendorRecord, register, utcnow_iso

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


@register
class PeptigrityScraper(BaseScraper):
    name = "peptigrity"
    source_url = "https://peptigrity.com/lab-tests"

    def scrape(self) -> list[VendorRecord]:
        html = self.fetch(self.source_url)
        if not html:
            return []
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 not installed; run `pip install beautifulsoup4`")

        soup = BeautifulSoup(html, "html.parser")
        records: dict[str, VendorRecord] = {}

        # Peptigrity renders test rows; we look for elements pairing a vendor name
        # with a trust score and a purity figure. This uses a generic table/row
        # heuristic so it degrades gracefully across layout changes.
        for row in soup.select("tr, li, div.card, div.lab-test"):
            text = row.get_text(" ", strip=True)
            if not text or len(text) > 400:
                continue
            score_m = re.search(r"(?:trust|score)[^0-9]{0,10}(\d{1,3})", text, re.I)
            purity_m = re.search(r"(\d{2,3}(?:\.\d)?)\s*%\s*(?:purity|pure|hplc)", text, re.I)
            vendor_m = re.search(r"(?:vendor|by|from)\s*[:\-]?\s*([A-Z][A-Za-z0-9 &\-]{2,40})", text)
            if not (score_m or purity_m) or not vendor_m:
                continue

            name = vendor_m.group(1).strip()
            rec = records.setdefault(name, VendorRecord(
                name=name,
                agg_source_name="Peptigrity",
                agg_source_url=self.source_url,
                publishes_coa="yes",
                sources=[{"title": f"Peptigrity - {name}", "url": self.source_url,
                          "retrieved_at": utcnow_iso()}],
            ))
            if score_m and rec.agg_score is None:
                rec.agg_score = float(score_m.group(1))
            if purity_m:
                rec.results.append({
                    "peptide": None,
                    "purity_pct": float(purity_m.group(1)),
                    "tests_count": 1,
                    "test_date": utcnow_iso(),
                    "source_name": "Peptigrity",
                    "source_url": self.source_url,
                })

        out = list(records.values())
        print(f"[peptigrity] scraped {len(out)} vendors")
        return out
