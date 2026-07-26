"""Accumark Labs COA scraper / verifier.

Accumark issues COAs with an "AccuVerify" code (e.g. WYGR-AJDT). KÖLD (kold.us)
uses Accumark. Unlike a flat image, the record is available as structured JSON
from a public WordPress REST route — so given a code we can pull the real
purity, quantity/fill, identity, endotoxin, and sterility values and turn each
COA into a test row.

Endpoint (discovered from the accuverify-badge web component):
    GET https://accumarklabs.com/wp-json/accumark/v1/badge/{CODE}
No auth / nonce required. Returns JSON with product_name, client_name,
sample_name, lot_code, date_completed, test_results[] (purity/identity/quantity)
and addon_results[] (endotoxin/sterility).

Getting codes: they're printed as a QR on each COA image, so at scale you OCR
the COA image (or scan the QR) to recover the code, then call this. Feed known
codes via the CODES list or the CLI.
"""
from __future__ import annotations

import sys
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from .base import BaseScraper, VendorRecord, register

API = "https://accumarklabs.com/wp-json/accumark/v1/badge/{code}"

# Known AccuVerify codes to harvest, as (code, vendor_name). Extend as you
# recover more codes (via OCR of COA images / scanning the QR).
KNOWN_CODES: list[tuple[str, str]] = [
    ("WYGR-AJDT", "KÖLD (kold.us)"),   # G3-R = Retatrutide, lot 1032
]


def _num(value) -> Optional[float]:
    """Pull a leading number out of e.g. '99.9%' or '10.37 mg'."""
    if value is None:
        return None
    s = str(value).strip().replace("%", "")
    import re
    m = re.match(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def parse_badge(js: dict) -> dict:
    """Turn an Accumark badge JSON payload into a normalised COA dict."""
    tests = {t.get("key") or t.get("test_name", "").lower(): t
             for t in js.get("test_results", [])}
    addons = {(a.get("test_name") or "").lower(): a for a in js.get("addon_results", [])}

    def _conforms(a) -> Optional[int]:
        if a is None:
            return None
        st = (a.get("status") or "").lower()
        if a.get("conforms") is True or st in ("pass", "passed", "conforms"):
            return 1
        if st in ("pending", "n/a", ""):
            return None
        return 0

    purity = None
    for k, t in tests.items():
        if "purit" in k or "purit" in (t.get("test_name", "").lower()):
            purity = _num(t.get("value"))
    quantity = None
    for k, t in tests.items():
        if "quant" in k or "quant" in (t.get("test_name", "").lower()):
            quantity = _num(t.get("value"))

    endo = next((a for name, a in addons.items() if "endotoxin" in name), None)
    ster = next((a for name, a in addons.items() if "steril" in name), None)

    return {
        "code": js.get("code"),
        "vendor": js.get("client_name"),
        "peptide": js.get("product_name"),
        "sample_name": js.get("sample_name"),
        "lot_code": js.get("lot_code"),
        "purity_pct": purity,
        "quantity_mg": quantity,
        "endotoxin_pass": _conforms(endo),
        "sterility_pass": _conforms(ster),
        "test_date": js.get("date_completed"),
        "overall_status": js.get("overall_status"),
        "verify_url": js.get("verify_url"),
    }


class AccumarkVerifier(BaseScraper):
    name = "accumark"
    source_url = "https://accumarklabs.com"

    def fetch_badge(self, code: str) -> Optional[dict]:
        if httpx is None:
            raise RuntimeError("httpx not installed")
        try:
            resp = httpx.get(API.format(code=code), timeout=self.timeout,
                             headers={"User-Agent": self.user_agent})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[accumark] fetch failed for {code}: {exc}")
            return None

    def verify_coa(self, code: str) -> Optional[dict]:
        js = self.fetch_badge(code)
        return parse_badge(js) if js else None

    def scrape(self) -> list[VendorRecord]:
        """Harvest all KNOWN_CODES into VendorRecords (one COA -> one test row)."""
        by_vendor: dict[str, VendorRecord] = {}
        for code, vendor in KNOWN_CODES:
            coa = self.verify_coa(code)
            if not coa:
                continue
            rec = by_vendor.setdefault(vendor, VendorRecord(name=vendor, publishes_coa="yes"))
            dosage = None
            # quantity vs a label mg parsed from sample size isn't in the badge;
            # store measured quantity in notes, purity/endotoxin/sterility as fields.
            rec.results.append({
                "peptide": coa["peptide"],
                "purity_pct": coa["purity_pct"],
                "dosage_accuracy_pct": dosage,
                "endotoxin_pass": coa["endotoxin_pass"],
                "sterility_pass": coa["sterility_pass"],
                "tests_count": 1,
                "test_date": coa["test_date"],
                "source_name": f"Accumark COA (verified {code})",
                "source_url": coa["verify_url"] or f"https://accumarklabs.com/verify?code={code}",
                "notes": f"Lot {coa['lot_code']}, measured {coa['quantity_mg']}mg, status {coa['overall_status']}.",
            })
        return list(by_vendor.values())


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python accumark.py <CODE>  (e.g. WYGR-AJDT)")
        sys.exit(1)
    coa = AccumarkVerifier().verify_coa(sys.argv[1])
    if not coa:
        print("No record / fetch failed.")
        sys.exit(2)
    for k, v in coa.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
