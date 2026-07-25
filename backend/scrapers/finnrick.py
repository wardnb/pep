"""Scraper for Finnrick (finnrick.com) — an independent aggregator publishing
thousands of third-party lab tests across ~275 vendors with a per-vendor
"safety %" composite and pass/fail counts.

NOTE ON RESPONSIBLE USE
-----------------------
Finnrick puts full COAs and lab names behind a paid tier. This scraper only
reads the PUBLIC vendor index / vendor pages (safety %, test count, pass/fail),
which is the same data a visitor sees for free. Respect the site's robots.txt
and terms; keep request rates low. Selectors below reflect the public page
structure and may need updating if the site changes its markup.
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
class FinnrickScraper(BaseScraper):
    name = "finnrick"
    source_url = "https://www.finnrick.com/vendors"

    # Public vendor slugs to poll. Extend this list, or discover it by parsing
    # the vendor index page (see discover_slugs()).
    SEED_SLUGS = [
        "peptide-sciences", "paradigm-peptides", "peptide-partners",
        "peptide-crafters",
    ]

    def discover_slugs(self) -> list[str]:
        """Parse the vendor index for /vendors/<slug> links (best-effort)."""
        html = self.fetch(self.source_url)
        if not html:
            return list(self.SEED_SLUGS)
        slugs = set(re.findall(r"/vendors/([a-z0-9\-]+)", html))
        return sorted(slugs) or list(self.SEED_SLUGS)

    def _parse_vendor_page(self, slug: str, html: str) -> Optional[VendorRecord]:
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 not installed; run `pip install beautifulsoup4`")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Safety percentage, e.g. "Safety 86%" or "86% safety score"
        pct_match = re.search(r"(\d{1,3})\s*%\s*(?:safety|score|safe)", text, re.I) \
            or re.search(r"safety[^0-9]{0,12}(\d{1,3})\s*%", text, re.I)
        agg_score = float(pct_match.group(1)) if pct_match else None

        # Test count, e.g. "130 tests" or "Tests 130"
        tests_match = re.search(r"(\d{1,4})\s+tests\b", text, re.I) \
            or re.search(r"tests[^0-9]{0,6}(\d{1,4})", text, re.I)
        agg_tests = int(tests_match.group(1)) if tests_match else None

        # Pass/fail, e.g. "78 pass 52 fail"
        pf = re.search(r"(\d{1,4})\s*pass[a-z]*[^0-9]{0,6}(\d{1,4})\s*fail", text, re.I)
        pass_count = int(pf.group(1)) if pf else None
        fail_count = int(pf.group(2)) if pf else None

        if agg_score is None and agg_tests is None:
            return None  # nothing useful parsed

        name = slug.replace("-", " ").title()
        url = f"https://www.finnrick.com/vendors/{slug}"
        rec = VendorRecord(
            name=name,
            agg_score=agg_score,
            agg_tests=agg_tests,
            agg_source_name="Finnrick",
            agg_source_url=url,
            publishes_coa="yes",  # presence of independent tests implies COAs exist
            sources=[{"title": f"Finnrick - {name}", "url": url,
                      "retrieved_at": utcnow_iso()}],
        )
        if pass_count is not None:
            rec.results.append({
                "peptide": "(aggregate)",
                "tests_count": agg_tests or (pass_count + (fail_count or 0)),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "test_date": utcnow_iso(),
                "source_name": "Finnrick",
                "source_url": url,
                "notes": "Aggregated pass/fail across published third-party tests.",
            })
        return rec

    def scrape(self) -> list[VendorRecord]:
        records: list[VendorRecord] = []
        for slug in self.discover_slugs():
            html = self.fetch(f"https://www.finnrick.com/vendors/{slug}")
            if not html:
                continue
            try:
                rec = self._parse_vendor_page(slug, html)
                if rec:
                    records.append(rec)
            except Exception as exc:  # noqa: BLE001
                print(f"[finnrick] parse failed for {slug}: {exc}")
        print(f"[finnrick] scraped {len(records)} vendors")
        return records
