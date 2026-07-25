"""Unit tests for the scoring engine. Run: python backend/test_scoring.py"""
from __future__ import annotations

from datetime import date, timedelta

import scoring
from scoring import (
    dosage_to_score, purity_to_score, score_vendor,
)


def approx(a, b, tol=0.5):
    return abs(a - b) <= tol


def test_purity_mapping():
    assert purity_to_score(99.5) == 100
    assert purity_to_score(99) == 100
    assert approx(purity_to_score(95), 60)
    assert approx(purity_to_score(90), 30)
    assert purity_to_score(0) == 0
    assert 30 < purity_to_score(97) < 100


def test_dosage_mapping():
    assert dosage_to_score(100) == 100
    assert dosage_to_score(103) == 100        # within +-5%
    assert dosage_to_score(65) == 0           # 35% off
    assert 0 < dosage_to_score(85) < 100


def test_unknowns_are_excluded_and_confidence_drops():
    # Vendor with ONLY a community score -> total == community, confidence == community weight.
    vendor = {"community_score": 1.0, "publishes_coa": "unknown"}
    vs = score_vendor(vendor, [], {})
    assert vs.total is not None
    assert approx(vs.total, 100)
    expected_conf = scoring.DEFAULT_WEIGHTS["community"] / sum(scoring.DEFAULT_WEIGHTS.values())
    assert approx(vs.confidence, expected_conf, 0.01)


def test_no_evidence_returns_none():
    vs = score_vendor({"publishes_coa": "unknown"}, [], {})
    assert vs.total is None
    assert vs.confidence == 0.0


def test_full_vendor_composite():
    labs = {1: {"id": 1, "name": "Vanguard", "accredited": 1}}
    recent = (date.today() - timedelta(days=30)).isoformat()
    vendor = {
        "publishes_coa": "yes", "community_score": 0.5,
        "agg_score": None, "agg_tests": None,
    }
    results = [
        {"lab_id": 1, "purity_pct": 99, "dosage_accuracy_pct": 100,
         "sterility_pass": 1, "endotoxin_pass": 1, "heavy_metals_pass": 1,
         "tests_count": 6, "test_date": recent},
    ]
    vs = score_vendor(vendor, results, labs)
    # Every dimension has evidence -> full confidence.
    assert approx(vs.confidence, 1.0, 0.01)
    assert vs.total > 85  # strong vendor
    for key in ("purity_dosage", "transparency", "community", "freshness",
                "sterility", "heavy_metals"):
        assert vs.dimensions[key].score is not None


def test_heavy_metals_dimension():
    from scoring import score_heavy_metals
    assert score_heavy_metals([]).score is None
    assert score_heavy_metals([{"heavy_metals_pass": 1}]).score == 100
    assert score_heavy_metals([{"heavy_metals_pass": 0}]).score == 0
    # heavy metals contributes to the composite and confidence
    vs = score_vendor({}, [{"heavy_metals_pass": 1, "test_date": "2026-07-01"}], {})
    assert vs.dimensions["heavy_metals"].score == 100


def test_stale_test_lowers_freshness():
    old = (date.today() - timedelta(days=3 * 365 + 10)).isoformat()
    vs = score_vendor({}, [{"purity_pct": 99, "test_date": old}], {})
    assert vs.dimensions["freshness"].score == 0.0


def test_aggregator_pass_rate():
    vendor = {"agg_score": None}
    results = [{"pass_count": 78, "fail_count": 52, "tests_count": 130}]
    vs = score_vendor(vendor, results, {})
    pd = vs.dimensions["purity_dosage"].score
    assert approx(pd, 60, 1)  # 78/130 = 60%


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} scoring tests passed.")


if __name__ == "__main__":
    run()
