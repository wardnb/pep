"""Vanguard Laboratory COA verifier / lister.

Vanguard ("Verified By Vanguard", verifiedbyvanguard.com) is an ISO 17025
accredited lab running the fullest panel in this space: purity, quantity,
identity, endotoxin, heavy metals (ICP-MS), sterility (USP <71>), plus fentanyl,
solubility, seal integrity. It exposes a PUBLIC REST API (no auth):

    GET https://verifiedbyvanguard.com/api/public-coas        # browse all records
    GET https://verifiedbyvanguard.com/api/verify/{uuid}      # one record (JSON)
    GET https://verifiedbyvanguard.com/api/brands             # client brands

Important: the public JSON reports WHICH tests were included + authenticity, but
the numeric results (purity %, ICP-MS values) live inside the linked PDF, not the
JSON. So this verifies scope + authenticity; measured values need the PDF.
"""
from __future__ import annotations

import sys
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from .base import BaseScraper, register

BASE = "https://verifiedbyvanguard.com"


@register
class VanguardVerifier(BaseScraper):
    name = "vanguard"
    source_url = BASE

    def _get(self, path: str) -> Optional[dict]:
        if httpx is None:
            raise RuntimeError("httpx not installed")
        try:
            resp = httpx.get(BASE + path, timeout=self.timeout,
                             headers={"User-Agent": self.user_agent})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[vanguard] fetch failed {path}: {exc}")
            return None

    def list_public_coas(self, search: str = "", min_purity: str = "") -> list[dict]:
        """Browse the public COA directory (optionally filtered)."""
        q = []
        if search:
            q.append(f"search={search}")
        if min_purity:
            q.append(f"minPurity={min_purity}")
        js = self._get("/api/public-coas" + ("?" + "&".join(q) if q else ""))
        if not js:
            return []
        return js if isinstance(js, list) else js.get("coas", js.get("data", []))

    def verify(self, uuid: str) -> Optional[dict]:
        """Verify one record by its UUID (orderNumber). Returns scope + status."""
        js = self._get(f"/api/verify/{uuid}")
        if not js or not js.get("verified"):
            return js
        included = [t.get("key") for t in js.get("tests", []) if t.get("state") == "included"]
        order = js.get("order", {})
        return {
            "verified": True,
            "coa_number": order.get("coaNumber"),
            "product": order.get("productName"),
            "vendor": (js.get("client") or {}).get("companyName"),
            "level": order.get("verificationLevel"),
            "completed_at": order.get("completedAt"),
            "tests_included": included,
            "sterility_method": js.get("sterilityMethod"),
            "pdf_url": BASE + (js.get("pdfUrl") or ""),
            "verify_url": f"{BASE}/verify/{uuid}",
        }

    def scrape(self):  # listing directory is heavy; not part of scheduled runs
        return []


def main() -> None:
    v = VanguardVerifier()
    if len(sys.argv) >= 2:
        import json
        print(json.dumps(v.verify(sys.argv[1]), indent=2))
    else:
        coas = v.list_public_coas()
        print(f"{len(coas)} public COAs. First few:")
        for c in coas[:5]:
            print(" ", c.get("productName"), "|", c.get("compound"), "|", c.get("coaNumber"))


if __name__ == "__main__":
    main()
