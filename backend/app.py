"""FastAPI application: serves the vendor-rating API and the frontend.

Run from the project root:
    uvicorn backend.app:app --reload
or use ./run.sh
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from repository import (
    all_results_grouped, get_labs_by_id, get_results_for_vendor,
    get_sources_for_vendor, get_vendor, list_vendors,
)
from scoring import DEFAULT_WEIGHTS, purity_to_score, score_vendor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="Peptide Vendor Rater", version="1.0")

_scheduler = None


@app.on_event("startup")
def _startup() -> None:
    init_db()
    _maybe_seed()
    _maybe_start_scheduler()


def _maybe_seed() -> None:
    """Auto-seed on first run if the vendors table is empty."""
    if not list_vendors():
        try:
            from seed import seed
            seed()
        except Exception as exc:  # noqa: BLE001
            print(f"[startup] auto-seed skipped: {exc}")


def _maybe_start_scheduler() -> None:
    global _scheduler
    if os.environ.get("DISABLE_SCHEDULER"):
        print("[startup] scheduler disabled via DISABLE_SCHEDULER")
        return
    try:
        from scheduler import build_scheduler
        _scheduler = build_scheduler()
        _scheduler.start()
        print("[startup] background scraper scheduler started")
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] scheduler not started: {exc}")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/meta")
def meta() -> dict:
    return {
        "weights": DEFAULT_WEIGHTS,
        "disclaimer": (
            "Ratings reflect the transparency and public third-party testing of each "
            "vendor, not an endorsement. Vendor marketing purity claims are treated as "
            "unverified unless tied to a verifiable COA. Aggregator scores (e.g. Finnrick) "
            "are directional only — Finnrick earns revenue from vendors it rates, so its "
            "numbers are not fully independent. Sourcing links to Chinese raw-material "
            "makers are community-rumored unless marked confirmed. Not medical advice."
        ),
    }


def _parse_us(raw):
    """Parse the vendors.us_presence JSON column into {level, note} or None."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


@app.get("/api/vendors")
def vendors() -> list[dict]:
    labs = get_labs_by_id()
    grouped = all_results_grouped()
    out = []
    for v in list_vendors():
        results = grouped.get(v["id"], [])
        score = score_vendor(v, results, labs)
        sd = score.as_dict()
        # A "flagged" community reputation (scam/impersonation/legal) discounts the
        # trust-adjusted score so a red-flag vendor can't sit at the top — the raw
        # COA "total" stays intact and honest, but Adjusted (the ranking column) drops.
        reputation = v["reputation"] or "unknown"
        if reputation == "flagged" and sd["adjusted"] is not None:
            sd["adjusted"] = max(0.0, round(sd["adjusted"] - 30, 1))
        out.append({
            "name": v["name"], "slug": v["slug"], "website": v["website"],
            "vendor_type": v["vendor_type"], "publishes_coa": v["publishes_coa"],
            "agg_source_name": v["agg_source_name"],
            "num_results": len(results),
            "reputation": reputation, "reputation_note": v["reputation_note"],
            "us_presence": _parse_us(v["us_presence"]),
            "score": sd,
        })
    # Sort by composite score (None last), then confidence.
    out.sort(key=lambda x: (
        x["score"]["total"] is not None,
        x["score"]["total"] or 0,
        x["score"]["confidence"],
    ), reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out


@app.get("/api/vendors/{slug}")
def vendor_detail(slug: str) -> dict:
    v = get_vendor(slug)
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    labs = get_labs_by_id()
    results = get_results_for_vendor(v["id"])
    score = score_vendor(v, results, labs)
    for r in results:
        r["lab_name"] = labs.get(r["lab_id"], {}).get("name") if r.get("lab_id") else None
    # Assemble verification / scam-check links: official domain first, then the
    # curated independent/warning links.
    verify = []
    if v.get("website"):
        verify.append({"label": "Official site — confirm you're here, not a lookalike",
                       "url": v["website"], "kind": "official"})
    try:
        verify.extend(json.loads(v["verify_links"]) if v.get("verify_links") else [])
    except (ValueError, TypeError):
        pass

    v["us_presence"] = _parse_us(v.get("us_presence"))
    return {
        "vendor": v,
        "score": score.as_dict(),
        "results": results,
        "sources": get_sources_for_vendor(v["id"]),
        "verify": verify,
    }


@app.get("/api/labs")
def labs() -> list[dict]:
    return list(get_labs_by_id().values())


# --------------------------------------------------------------------------- #
# Per-peptide view
# --------------------------------------------------------------------------- #
def _normalize_peptide(name: str) -> Optional[str]:
    """Canonicalize a peptide label, or None to skip (blends / aggregate rows)."""
    n = (name or "").strip()
    if not n or n.startswith("(") or "/" in n:
        return None
    low = n.lower()
    aliases = {
        "ghk-cu": "GHK-Cu", "bpc-157": "BPC-157", "tb-500": "TB-500",
        "pt-141": "PT-141", "ss-31": "SS-31", "cjc-1295": "CJC-1295",
        "cjc-1295 with dac": "CJC-1295", "cjc-1295 without dac": "CJC-1295",
        "melanotan ii": "Melanotan II", "melanotan i": "Melanotan I",
        "nad+": "NAD+", "hgh fragment 176-191": "HGH Fragment 176-191",
    }
    return aliases.get(low, n)


def _peptide_index():
    grouped = all_results_grouped()
    vendors = {v["id"]: v for v in list_vendors()}
    idx: dict = {}
    for vid, rows in grouped.items():
        for r in rows:
            pep = _normalize_peptide(r.get("peptide"))
            if not pep:
                continue
            d = idx.setdefault(pep, {}).setdefault(vid, {
                "ratings": [], "purities": [], "tests": 0, "dates": [], "sources": set(),
                "prices": []})
            if r.get("price_per_mg") is not None:
                d["prices"].append(r["price_per_mg"])
            if r.get("peptide_rating") is not None:
                d["ratings"].append(r["peptide_rating"])
            if r.get("purity_pct") is not None:
                d["purities"].append(r["purity_pct"])
            d["tests"] += r.get("tests_count") or 1
            if r.get("test_date"):
                d["dates"].append(r["test_date"])
            if r.get("source_name"):
                d["sources"].add(r["source_name"])
    return idx, vendors


def _rank_for_peptide(pep: str, idx: dict, vendors: dict) -> list[dict]:
    out = []
    for vid, d in idx.get(pep, {}).items():
        v = vendors.get(vid)
        if not v:
            continue
        rating = max(d["ratings"]) if d["ratings"] else None
        purity = round(sum(d["purities"]) / len(d["purities"]), 2) if d["purities"] else None
        score = rating if rating is not None else (purity_to_score(purity) if purity is not None else None)
        # Volume-weighted adjusted score so a single test can't outrank 30.
        # Full weight at >= 8 tests; shrink toward a neutral 50 below that.
        weight = min(d["tests"] / 8.0, 1.0)
        adj = score * weight + 50 * (1 - weight) if score is not None else None
        out.append({
            "vendor": v["name"], "slug": v["slug"], "vendor_type": v["vendor_type"],
            "reputation": v["reputation"] or "unknown",
            "us_presence": _parse_us(v["us_presence"]),
            "score": round(score, 1) if score is not None else None,
            "adjusted": round(adj, 1) if adj is not None else None,
            "rating": rating, "purity": purity, "tests": d["tests"],
            "price_per_mg": min(d["prices"]) if d["prices"] else None,
            "latest": max(d["dates"]) if d["dates"] else None,
            "sources": sorted(d["sources"]),
        })
    out.sort(key=lambda x: (x["adjusted"] is not None, x["adjusted"] or 0, x["tests"]), reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out


# Clinical-trial REFERENCE titrations — what published trials did (supervised
# research), NOT a dosing recommendation. Shown as an info banner in the app.
PEPTIDE_REFERENCE = {
    "Retatrutide": {
        "title": "Clinical-trial reference — Phase 2 (NCT04881760, NEJM 2023). Not a dosing recommendation; supervised research.",
        "text": ("Once-weekly subcutaneous. Escalation arms started at 2 mg/week and "
                 "stepped up ~every 4 weeks (2→4→8→12 mg). E.g. 12 mg target: "
                 "2 mg wks 1-4, 4 mg wks 5-8, 8 mg wks 9-12, 12 mg thereafter. The 2 mg "
                 "start was used to reduce GI side effects. Investigational drug, not FDA-approved."),
        "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2301972",
    },
}


@app.get("/api/peptides")
def peptides() -> list[dict]:
    idx, vendors = _peptide_index()
    out = [{"name": pep, "vendors": len(vs),
            "tests": sum(d["tests"] for d in vs.values()),
            "reference": PEPTIDE_REFERENCE.get(pep)}
           for pep, vs in idx.items()]
    out.sort(key=lambda x: (x["vendors"], x["tests"]), reverse=True)
    return out


@app.get("/api/peptides/{name}")
def peptide_detail(name: str) -> dict:
    idx, vendors = _peptide_index()
    canon = _normalize_peptide(name) or name
    return {"peptide": canon, "vendors": _rank_for_peptide(canon, idx, vendors)}


@app.post("/api/refresh")
def refresh() -> dict:
    """Manually trigger a scraper refresh run."""
    from ingest import run_all
    summary = run_all()
    return {"status": "ok", "summary": summary}


@app.post("/api/verify/janoshik")
def verify_janoshik(payload: dict) -> dict:
    """Verify a Janoshik COA by task number + unique key (from the printed COA)."""
    from scrapers.janoshik import JanoshikVerifier
    task = (payload or {}).get("task_number")
    key = (payload or {}).get("unique_key")
    if not task or not key:
        raise HTTPException(status_code=400,
                            detail="Provide task_number and unique_key")
    return JanoshikVerifier().verify_coa(str(task), str(key))


@app.post("/api/verify/accumark")
def verify_accumark(payload: dict) -> dict:
    """Pull a structured Accumark COA by its AccuVerify code (e.g. WYGR-AJDT)."""
    from scrapers.accumark import AccumarkVerifier
    code = (payload or {}).get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Provide code")
    coa = AccumarkVerifier().verify_coa(str(code))
    if not coa:
        raise HTTPException(status_code=404, detail="No record / fetch failed")
    return coa


# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
