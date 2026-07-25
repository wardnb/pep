"""Scoring engine for peptide vendors.

Produces a transparent, weighted composite rating (0-100) from five dimensions:

    purity_dosage  - measured lab purity + fill/dose accuracy + aggregator pass rate
    transparency   - publishes third-party COAs, uses accredited labs, test volume
    community      - community reputation sentiment
    freshness      - how recent the most recent test is
    sterility      - whether sterility/endotoxin panels were run and passed

Design principles
-----------------
* Every dimension is scored 0-100 independently, or returned as ``None`` when
  there is no evidence for it.
* The composite only averages the dimensions that HAVE evidence, renormalising
  the weights. This avoids punishing a vendor for a dimension we simply cannot
  observe, while a separate ``confidence`` value (0-1) reports how much of the
  intended weight was actually backed by data.
* Nothing here invents data. Missing signal -> ``None`` -> excluded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

# Default dimension weights (must be > 0). Tune freely; they are renormalised.
DEFAULT_WEIGHTS = {
    "purity_dosage": 0.30,
    "transparency": 0.18,
    "community": 0.12,
    "freshness": 0.12,
    "sterility": 0.13,
    "heavy_metals": 0.15,
}

# A test older than this (days) contributes no freshness credit.
FRESHNESS_MAX_AGE_DAYS = 3 * 365
# A test newer than this (days) gets full freshness credit.
FRESHNESS_FULL_CREDIT_DAYS = 180


@dataclass
class Dimension:
    key: str
    score: Optional[float]      # 0-100, or None when unknown
    detail: str = ""


# Neutral baseline that low-confidence scores are shrunk toward for ranking.
NEUTRAL_BASELINE = 50.0


@dataclass
class VendorScore:
    total: Optional[float]                 # 0-100 composite, or None when no evidence at all
    confidence: float                      # 0-1: fraction of intended weight backed by data
    dimensions: dict = field(default_factory=dict)  # key -> Dimension

    @property
    def adjusted(self) -> Optional[float]:
        """Confidence-adjusted score: shrink the composite toward a neutral 50
        in proportion to how little data backs it. A 95 backed by one weak
        signal lands far below a 90 backed by full evidence.
        """
        if self.total is None:
            return None
        return self.total * self.confidence + NEUTRAL_BASELINE * (1 - self.confidence)

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 1) if self.total is not None else None,
            "adjusted": round(self.adjusted, 1) if self.adjusted is not None else None,
            "confidence": round(self.confidence, 2),
            "dimensions": {
                k: {"score": round(d.score, 1) if d.score is not None else None,
                    "detail": d.detail}
                for k, d in self.dimensions.items()
            },
        }


# --------------------------------------------------------------------------- #
# Helper mappings
# --------------------------------------------------------------------------- #
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def purity_to_score(purity_pct: float) -> float:
    """Map an HPLC purity percentage to a 0-100 subscore.

    Anchored on the community's informal >=99% standard. Below 90% falls off fast.
    """
    if purity_pct >= 99:
        return 100.0
    if purity_pct >= 95:
        # 95 -> 60, 99 -> 100
        return _clamp(60 + (purity_pct - 95) * (40 / 4))
    if purity_pct >= 90:
        # 90 -> 30, 95 -> 60
        return _clamp(30 + (purity_pct - 90) * (30 / 5))
    # 0 -> 0, 90 -> 30
    return _clamp(purity_pct * (30 / 90))


def dosage_to_score(dosage_accuracy_pct: float) -> float:
    """Map measured fill vs label (100 = perfect) to a 0-100 subscore.

    Deviation in either direction is penalised. +-5% ~ excellent, +-35% ~ zero.
    """
    deviation = abs(dosage_accuracy_pct - 100)
    if deviation <= 5:
        return 100.0
    if deviation >= 35:
        return 0.0
    return _clamp(100 - (deviation - 5) * (100 / 30))


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Dimension scorers
# --------------------------------------------------------------------------- #
def score_purity_dosage(vendor: dict, results: list[dict]) -> Dimension:
    """Blend granular purity/dosage/pass-rate results with an aggregator composite."""
    parts: list[float] = []
    notes: list[str] = []

    purities = [r["purity_pct"] for r in results if r.get("purity_pct") is not None]
    if purities:
        avg_p = sum(purities) / len(purities)
        parts.append(purity_to_score(avg_p))
        notes.append(f"avg purity {avg_p:.1f}% (n={len(purities)})")

    dosages = [r["dosage_accuracy_pct"] for r in results if r.get("dosage_accuracy_pct") is not None]
    if dosages:
        avg_d = sum(dosages) / len(dosages)
        parts.append(dosage_to_score(avg_d))
        notes.append(f"avg fill {avg_d:.0f}% of label")

    # Aggregator pass rate (e.g. Finnrick pass/fail counts across many assays)
    pass_c = sum(r.get("pass_count") or 0 for r in results)
    fail_c = sum(r.get("fail_count") or 0 for r in results)
    if pass_c + fail_c > 0:
        rate = 100 * pass_c / (pass_c + fail_c)
        parts.append(rate)
        notes.append(f"{pass_c}/{pass_c + fail_c} independent assays passed")

    # External aggregator composite score (already 0-100)
    if vendor.get("agg_score") is not None:
        parts.append(float(vendor["agg_score"]))
        src = vendor.get("agg_source_name") or "aggregator"
        n = vendor.get("agg_tests")
        notes.append(f"{src} score {vendor['agg_score']:.0f}%" + (f" ({n} tests)" if n else ""))

    if not parts:
        return Dimension("purity_dosage", None, "no quantitative lab results found")
    return Dimension("purity_dosage", sum(parts) / len(parts), "; ".join(notes))


def score_transparency(vendor: dict, results: list[dict], labs_by_id: dict) -> Dimension:
    """COA publishing + accredited-lab use + independent test volume."""
    coa_map = {"yes": 100, "partial": 55, "no": 0}
    coa = str(vendor.get("publishes_coa") or "unknown").lower()
    parts: list[float] = []
    notes: list[str] = []

    if coa in coa_map:
        parts.append(coa_map[coa])
        notes.append(f"COAs: {coa}")

    # Accredited lab usage
    lab_ids = {r["lab_id"] for r in results if r.get("lab_id")}
    if lab_ids:
        accredited = any(labs_by_id.get(lid, {}).get("accredited") for lid in lab_ids)
        parts.append(100 if accredited else 55)
        notes.append("accredited lab used" if accredited else "non-accredited lab used")

    # Test volume: more independent data points -> more transparency (caps at 12)
    total_tests = sum(r.get("tests_count") or 1 for r in results)
    if vendor.get("agg_tests"):
        total_tests = max(total_tests, vendor["agg_tests"])
    if total_tests > 0:
        parts.append(_clamp(total_tests / 12 * 100))
        notes.append(f"{total_tests} public tests")

    if not parts:
        return Dimension("transparency", None, "no transparency signals found")
    return Dimension("transparency", sum(parts) / len(parts), "; ".join(notes))


def score_community(vendor: dict) -> Dimension:
    cs = vendor.get("community_score")
    if cs is None:
        return Dimension("community", None, "no community sentiment recorded")
    # map -1..+1 -> 0..100
    score = _clamp((cs + 1) / 2 * 100)
    return Dimension("community", score, vendor.get("community_notes") or "")


def score_freshness(results: list[dict]) -> Dimension:
    dates = [d for d in (_parse_date(r.get("test_date")) for r in results) if d]
    if not dates:
        return Dimension("freshness", None, "no dated tests")
    most_recent = max(dates)
    age_days = (date.today() - most_recent).days
    if age_days <= FRESHNESS_FULL_CREDIT_DAYS:
        score = 100.0
    elif age_days >= FRESHNESS_MAX_AGE_DAYS:
        score = 0.0
    else:
        span = FRESHNESS_MAX_AGE_DAYS - FRESHNESS_FULL_CREDIT_DAYS
        score = _clamp(100 * (1 - (age_days - FRESHNESS_FULL_CREDIT_DAYS) / span))
    return Dimension("freshness", score, f"most recent test {most_recent.isoformat()} ({age_days}d ago)")


def score_sterility(results: list[dict]) -> Dimension:
    tested = [r for r in results
              if r.get("sterility_pass") is not None or r.get("endotoxin_pass") is not None]
    if not tested:
        return Dimension("sterility", None, "no sterility/endotoxin testing found")
    flags: list[int] = []
    for r in tested:
        for key in ("sterility_pass", "endotoxin_pass"):
            if r.get(key) is not None:
                flags.append(1 if r[key] else 0)
    score = 100 * sum(flags) / len(flags)
    passed = sum(flags)
    return Dimension("sterility", score, f"{passed}/{len(flags)} sterility/endotoxin panels passed")


def score_heavy_metals(results: list[dict]) -> Dimension:
    """ICP-MS heavy-metals screening (lead, arsenic, cadmium, mercury)."""
    tested = [r for r in results if r.get("heavy_metals_pass") is not None]
    if not tested:
        return Dimension("heavy_metals", None, "no heavy-metals/ICP-MS testing found")
    flags = [1 if r["heavy_metals_pass"] else 0 for r in tested]
    score = 100 * sum(flags) / len(flags)
    return Dimension("heavy_metals", score,
                     f"{sum(flags)}/{len(flags)} ICP-MS heavy-metals panels within limits")


# --------------------------------------------------------------------------- #
# Composite
# --------------------------------------------------------------------------- #
def score_vendor(vendor: dict, results: list[dict], labs_by_id: dict,
                 weights: Optional[dict] = None) -> VendorScore:
    w = dict(weights or DEFAULT_WEIGHTS)
    dims = {
        "purity_dosage": score_purity_dosage(vendor, results),
        "transparency": score_transparency(vendor, results, labs_by_id),
        "community": score_community(vendor),
        "freshness": score_freshness(results),
        "sterility": score_sterility(results),
        "heavy_metals": score_heavy_metals(results),
    }

    weighted_sum = 0.0
    covered_weight = 0.0
    for key, dim in dims.items():
        if dim.score is not None:
            weighted_sum += dim.score * w[key]
            covered_weight += w[key]

    total_weight = sum(w.values())
    if covered_weight == 0:
        return VendorScore(total=None, confidence=0.0, dimensions=dims)

    total = weighted_sum / covered_weight
    confidence = covered_weight / total_weight
    return VendorScore(total=total, confidence=confidence, dimensions=dims)
