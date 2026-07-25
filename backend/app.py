"""FastAPI application: serves the vendor-rating API and the frontend.

Run from the project root:
    uvicorn backend.app:app --reload
or use ./run.sh
"""
from __future__ import annotations

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
from scoring import DEFAULT_WEIGHTS, score_vendor

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


@app.get("/api/vendors")
def vendors() -> list[dict]:
    labs = get_labs_by_id()
    grouped = all_results_grouped()
    out = []
    for v in list_vendors():
        results = grouped.get(v["id"], [])
        score = score_vendor(v, results, labs)
        out.append({
            "name": v["name"], "slug": v["slug"], "website": v["website"],
            "vendor_type": v["vendor_type"], "publishes_coa": v["publishes_coa"],
            "agg_source_name": v["agg_source_name"],
            "num_results": len(results),
            "score": score.as_dict(),
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
    return {
        "vendor": v,
        "score": score.as_dict(),
        "results": results,
        "sources": get_sources_for_vendor(v["id"]),
    }


@app.get("/api/labs")
def labs() -> list[dict]:
    return list(get_labs_by_id().values())


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


# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
