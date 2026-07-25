"""Data-access helpers sitting between the database and the API/scoring layers."""
from __future__ import annotations

from typing import Optional

from database import get_connection


def _row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def get_labs_by_id() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM labs").fetchall()
    return {r["id"]: _row_to_dict(r) for r in rows}


def list_vendors() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM vendors ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_vendor(slug: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM vendors WHERE slug = ?", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def get_results_for_vendor(vendor_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM test_results WHERE vendor_id = ? ORDER BY test_date DESC",
            (vendor_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_sources_for_vendor(vendor_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vendor_sources WHERE vendor_id = ?", (vendor_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def all_results_grouped() -> dict:
    """Return {vendor_id: [result dicts]} for every vendor in one pass."""
    grouped: dict = {}
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM test_results").fetchall()
    for r in rows:
        grouped.setdefault(r["vendor_id"], []).append(_row_to_dict(r))
    return grouped


# --------------------------------------------------------------------------- #
# Upserts (used by seeding and scrapers)
# --------------------------------------------------------------------------- #
def upsert_lab(conn, name: str, location=None, accredited=0,
               capabilities=None, verification_url=None) -> int:
    cur = conn.execute(
        """INSERT INTO labs (name, location, accredited, capabilities, verification_url)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             location=COALESCE(excluded.location, labs.location),
             accredited=excluded.accredited,
             capabilities=COALESCE(excluded.capabilities, labs.capabilities),
             verification_url=COALESCE(excluded.verification_url, labs.verification_url)""",
        (name, location, accredited, capabilities, verification_url),
    )
    if cur.lastrowid:
        row = conn.execute("SELECT id FROM labs WHERE name = ?", (name,)).fetchone()
        return row["id"]
    return conn.execute("SELECT id FROM labs WHERE name = ?", (name,)).fetchone()["id"]


def upsert_vendor(conn, vendor: dict) -> int:
    """Insert or update a vendor by slug. Returns vendor id."""
    conn.execute(
        """INSERT INTO vendors
             (name, slug, website, vendor_type, sourcing_notes, publishes_coa,
              community_score, community_notes,
              agg_score, agg_tests, agg_source_name, agg_source_url, notes, updated_at)
           VALUES
             (:name, :slug, :website, :vendor_type, :sourcing_notes, :publishes_coa,
              :community_score, :community_notes,
              :agg_score, :agg_tests, :agg_source_name, :agg_source_url, :notes, datetime('now'))
           ON CONFLICT(slug) DO UPDATE SET
             name=excluded.name,
             website=COALESCE(excluded.website, vendors.website),
             vendor_type=excluded.vendor_type,
             sourcing_notes=COALESCE(excluded.sourcing_notes, vendors.sourcing_notes),
             publishes_coa=excluded.publishes_coa,
             community_score=COALESCE(excluded.community_score, vendors.community_score),
             community_notes=COALESCE(excluded.community_notes, vendors.community_notes),
             agg_score=COALESCE(excluded.agg_score, vendors.agg_score),
             agg_tests=COALESCE(excluded.agg_tests, vendors.agg_tests),
             agg_source_name=COALESCE(excluded.agg_source_name, vendors.agg_source_name),
             agg_source_url=COALESCE(excluded.agg_source_url, vendors.agg_source_url),
             notes=COALESCE(excluded.notes, vendors.notes),
             updated_at=datetime('now')""",
        {
            "name": vendor["name"],
            "slug": vendor["slug"],
            "website": vendor.get("website"),
            "vendor_type": vendor.get("vendor_type", "consumer"),
            "sourcing_notes": vendor.get("sourcing_notes"),
            "publishes_coa": vendor.get("publishes_coa", "unknown"),
            "community_score": vendor.get("community_score"),
            "community_notes": vendor.get("community_notes"),
            "agg_score": vendor.get("agg_score"),
            "agg_tests": vendor.get("agg_tests"),
            "agg_source_name": vendor.get("agg_source_name"),
            "agg_source_url": vendor.get("agg_source_url"),
            "notes": vendor.get("notes"),
        },
    )
    return conn.execute("SELECT id FROM vendors WHERE slug = ?", (vendor["slug"],)).fetchone()["id"]


def add_test_result(conn, vendor_id: int, result: dict, lab_id: Optional[int] = None) -> None:
    conn.execute(
        """INSERT INTO test_results
             (vendor_id, lab_id, peptide, purity_pct, dosage_accuracy_pct,
              sterility_pass, endotoxin_pass, heavy_metals_pass, tests_count,
              pass_count, fail_count, test_date, source_name, source_url, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            vendor_id, lab_id, result.get("peptide"), result.get("purity_pct"),
            result.get("dosage_accuracy_pct"), result.get("sterility_pass"),
            result.get("endotoxin_pass"), result.get("heavy_metals_pass"),
            result.get("tests_count", 1),
            result.get("pass_count"), result.get("fail_count"),
            result.get("test_date"), result.get("source_name"),
            result.get("source_url"), result.get("notes"),
        ),
    )


def add_source(conn, vendor_id: int, title: str, url: str, retrieved_at: str) -> None:
    conn.execute(
        "INSERT INTO vendor_sources (vendor_id, title, url, retrieved_at) VALUES (?, ?, ?, ?)",
        (vendor_id, title, url, retrieved_at),
    )
