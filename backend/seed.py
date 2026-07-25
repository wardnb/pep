"""Seed the database from data/seed_data.json (the live-research dataset)."""
from __future__ import annotations

import json
from pathlib import Path

from database import DB_PATH, get_connection, init_db
from repository import add_source, add_test_result, upsert_lab, upsert_vendor

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_data.json"


def seed(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing database at {DB_PATH}")

    init_db()
    data = json.loads(SEED_PATH.read_text())

    with get_connection() as conn:
        # Labs first so results can reference them by name.
        lab_ids: dict[str, int] = {}
        for lab in data.get("labs", []):
            lab_ids[lab["name"]] = upsert_lab(
                conn,
                name=lab["name"],
                location=lab.get("location"),
                accredited=lab.get("accredited", 0),
                capabilities=lab.get("capabilities"),
                verification_url=lab.get("verification_url"),
            )

        vendor_count = result_count = 0
        for v in data.get("vendors", []):
            vendor_dict = {
                "name": v["name"],
                "slug": _slug(v["name"]),
                "website": v.get("website"),
                "vendor_type": v.get("vendor_type", "consumer"),
                "sourcing_notes": v.get("sourcing_notes"),
                "publishes_coa": v.get("publishes_coa", "unknown"),
                "community_score": v.get("community_score"),
                "community_notes": v.get("community_notes"),
                "agg_score": v.get("agg_score"),
                "agg_tests": v.get("agg_tests"),
                "agg_source_name": v.get("agg_source_name"),
                "agg_source_url": v.get("agg_source_url"),
                "notes": v.get("notes"),
            }
            vid = upsert_vendor(conn, vendor_dict)
            vendor_count += 1

            for r in v.get("results", []):
                lab_id = lab_ids.get(r.get("lab_name")) if r.get("lab_name") else None
                add_test_result(conn, vid, r, lab_id=lab_id)
                result_count += 1

            for s in v.get("sources", []):
                add_source(conn, vid, s.get("title", ""), s.get("url", ""),
                           s.get("retrieved_at", ""))

        conn.commit()

    print(f"Seeded {vendor_count} vendors, {result_count} test results, "
          f"{len(data.get('labs', []))} labs into {DB_PATH}")


def _slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name.strip()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


if __name__ == "__main__":
    import sys
    seed(reset="--reset" in sys.argv)
