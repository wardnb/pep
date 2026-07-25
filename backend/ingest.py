"""Ingest layer: run scrapers and persist their VendorRecords into the DB.

Kept separate from the scrapers themselves so scrapers stay pure (fetch+parse)
and this module owns all database writes.
"""
from __future__ import annotations

import scrapers  # noqa: F401  (ensures scrapers are registered)
from database import get_connection, init_db
from repository import add_source, add_test_result, upsert_vendor
from scrapers.base import VendorRecord, available_scrapers, get_scraper


def persist_records(records: list[VendorRecord]) -> int:
    """Upsert a batch of scraped records. Returns number of vendors written."""
    written = 0
    with get_connection() as conn:
        for rec in records:
            vendor_id = upsert_vendor(conn, rec.to_vendor_dict())
            for result in rec.results:
                add_test_result(conn, vendor_id, result)
            for src in rec.sources:
                add_source(conn, vendor_id, src.get("title", ""),
                           src.get("url", ""), src.get("retrieved_at", ""))
            written += 1
        conn.commit()
    return written


def run_scraper(name: str) -> int:
    scraper = get_scraper(name)
    records = scraper.scrape()
    count = persist_records(records)
    print(f"[ingest] {name}: persisted {count} vendors")
    return count


def run_all(names: list[str] | None = None) -> dict:
    init_db()
    names = names or available_scrapers()
    summary = {}
    for name in names:
        try:
            summary[name] = run_scraper(name)
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] scraper '{name}' errored: {exc}")
            summary[name] = 0
    return summary


if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] or None
    result = run_all(targets)
    print("Ingest summary:", result)
