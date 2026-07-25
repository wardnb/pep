"""SQLite database layer for the peptide vendor rater.

Uses the standard-library ``sqlite3`` module (no ORM) so the code stays easy to
read and modify. A single database file lives at ``data/peptides.db``.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# data/peptides.db, resolved relative to the project root (parent of backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "peptides.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS labs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    location      TEXT,
    accredited    INTEGER DEFAULT 0,          -- 1 if ISO/IEC 17025 (or equivalent) accredited
    capabilities  TEXT,                        -- free text: HPLC, LC-MS, endotoxin, ICP-MS...
    verification_url TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    slug          TEXT UNIQUE NOT NULL,
    website       TEXT,
    -- 'consumer' (retail brand) or 'raws' (upstream raw-material manufacturer)
    vendor_type   TEXT DEFAULT 'consumer',
    -- where this vendor is reported to source from (free text; flag rumor vs confirmed)
    sourcing_notes TEXT,
    -- transparency signals
    publishes_coa TEXT DEFAULT 'unknown',      -- 'yes' | 'partial' | 'no' | 'unknown'
    -- community reputation on a -1..+1 scale (-1 controversial, 0 neutral/unknown, +1 strong)
    community_score REAL,
    community_notes TEXT,
    -- external aggregator composite (e.g. Finnrick "safety %"): a 0-100 quality signal
    agg_score       REAL,
    agg_tests       INTEGER,
    agg_source_name TEXT,
    agg_source_url  TEXT,
    notes         TEXT,
    updated_at    TEXT DEFAULT (datetime('now'))
);

-- One row per published test data point (a vendor may have many across peptides/labs).
CREATE TABLE IF NOT EXISTS test_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id     INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    lab_id        INTEGER REFERENCES labs(id),
    peptide       TEXT,                         -- e.g. 'Semaglutide', 'BPC-157'
    purity_pct    REAL,                         -- measured HPLC purity, 0-100
    dosage_accuracy_pct REAL,                   -- measured fill vs label, 100 = perfect
    sterility_pass  INTEGER,                    -- 1 pass / 0 fail / NULL not tested
    endotoxin_pass  INTEGER,                    -- 1 pass / 0 fail / NULL not tested
    heavy_metals_pass INTEGER,                  -- 1 pass / 0 fail / NULL not tested (ICP-MS)
    tests_count   INTEGER DEFAULT 1,            -- number of underlying assays this row summarizes
    pass_count    INTEGER,                      -- assays that passed vendor/aggregator standard
    fail_count    INTEGER,
    test_date     TEXT,                         -- ISO date of the most recent underlying test
    source_name   TEXT,
    source_url    TEXT,
    notes         TEXT
);

-- Citations / provenance rows attached to a vendor.
CREATE TABLE IF NOT EXISTS vendor_sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id     INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    title         TEXT,
    url           TEXT,
    retrieved_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_results_vendor ON test_results(vendor_id);
CREATE INDEX IF NOT EXISTS idx_sources_vendor ON vendor_sources(vendor_id);
"""


def get_connection() -> sqlite3.Connection:
    """Return a connection with row access by column name and FK enforcement."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not yet exist."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


if __name__ == "__main__":
    init_db()
    print(f"Initialised database at {DB_PATH}")
