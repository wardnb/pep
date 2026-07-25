"""Scraper for kold.us (KÖLD Peptides) — the vendor that kicked off this project.

KÖLD publishes per-lot COAs in a "COA Library" on its Quality page. Notably the
COAs are issued by **Accumark Labs** (Anaheim, CA) — not the community-standard
Janoshik — and each carries a QR to Accumark's own verification portal
(accumarklabs.com/verify/XXXX-XXXX). The COAs seen publish HPLC purity, identity,
and fill/quantity, but no heavy-metals/ICP-MS, sterility, or endotoxin data.

This scraper lists the published COA files (purity often appears in the filename
or nearby text) and records them as sources so the app can track testing volume
and recency. Full numeric purity for each lot lives inside the COA image/PDF and
would need OCR to extract — out of scope here, but the file links are captured.
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
class KoldScraper(BaseScraper):
    name = "kold"
    source_url = "https://kold.us/quality/"

    def scrape(self) -> list[VendorRecord]:
        html = self.fetch(self.source_url)
        if not html:
            return []
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 not installed")
        soup = BeautifulSoup(html, "html.parser")

        # Collect links that look like COA files (images/PDFs under uploads).
        coa_links = []
        for a in soup.find_all(["a", "img"]):
            href = a.get("href") or a.get("src") or ""
            if re.search(r"coa|/uploads/.*\.(png|jpg|jpeg|pdf)", href, re.I):
                coa_links.append(href)
        coa_links = list(dict.fromkeys(coa_links))  # dedupe, keep order

        rec = VendorRecord(
            name="KÖLD (kold.us)",
            website="https://kold.us",
            publishes_coa="partial",
            notes=("COAs issued by Accumark Labs (Anaheim, CA), verified via "
                   "accumarklabs.com QR. Published COAs cover HPLC purity/identity/"
                   "fill only — no heavy-metals, sterility, or endotoxin data."),
            sources=[{"title": "KÖLD Quality / COA library", "url": self.source_url,
                      "retrieved_at": utcnow_iso()}],
        )
        # Record each COA file as a datable source (recency signal).
        for link in coa_links[:25]:
            url = link if link.startswith("http") else "https://kold.us" + link
            rec.sources.append({"title": f"KÖLD COA: {link.rsplit('/', 1)[-1]}",
                                 "url": url, "retrieved_at": utcnow_iso()})

        # If a COA count is found, log it as a testing-volume result.
        if coa_links:
            rec.results.append({
                "peptide": "(COA library)", "tests_count": len(coa_links),
                "test_date": utcnow_iso(), "source_name": "kold.us / Accumark Labs",
                "source_url": self.source_url,
                "notes": f"{len(coa_links)} per-lot COA files published (Accumark Labs).",
            })
        print(f"[kold] found {len(coa_links)} COA files")
        return [rec]
