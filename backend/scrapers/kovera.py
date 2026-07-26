"""Kovera Labs COA verifier — single-code lookup only.

Kovera Labs (koveralabs.com) runs HPLC/LC-MS purity + identity with ICP-MS
heavy-metals, endotoxin (LAL), and 14-day sterility add-ons. Its verify feature
is backed by a public Supabase RPC:

    POST {SUPABASE_URL}/rest/v1/rpc/verify_coa_by_code   body {"p_code": "KVR-2026-XXXXXX"}

RESPONSIBLE-USE NOTE
--------------------
This verifier looks up EXACTLY ONE code that you already have (off a COA you're
holding). It deliberately does NOT enumerate, fuzzy-match, or bulk-scan codes —
that would be scraping other parties' records. It also does NOT bundle Kovera's
API key: supply the Supabase URL + anon key via env vars (KOVERA_SUPABASE_URL,
KOVERA_ANON_KEY) so the operator opts in explicitly. Prefer using vendors'
own published COA PDFs for dataset values.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None


def verify_code(code: str, supabase_url: Optional[str] = None,
                anon_key: Optional[str] = None, timeout: float = 20.0) -> Optional[dict]:
    """Look up a single Kovera COA by its printed code. Returns normalised fields."""
    if httpx is None:
        raise RuntimeError("httpx not installed")
    supabase_url = supabase_url or os.environ.get("KOVERA_SUPABASE_URL")
    anon_key = anon_key or os.environ.get("KOVERA_ANON_KEY")
    if not supabase_url or not anon_key:
        raise RuntimeError(
            "Set KOVERA_SUPABASE_URL and KOVERA_ANON_KEY env vars (from Kovera's "
            "public site config) to enable single-code lookup.")
    try:
        resp = httpx.post(
            f"{supabase_url}/rest/v1/rpc/verify_coa_by_code",
            headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}",
                     "Content-Type": "application/json"},
            json={"p_code": code.upper()}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[kovera] lookup failed for {code}: {exc}")
        return None

    coas = data.get("coas") if isinstance(data, dict) else data
    if not coas:
        return {"code": code, "found": False}
    main_coa = next((c for c in coas if not c.get("coa_type")), coas[0])
    results = main_coa.get("results", {}) or {}
    hm = next((c for c in coas if c.get("coa_type") == "heavy_metals"), None)
    return {
        "code": code, "found": True,
        "peptide": main_coa.get("peptide_name"),
        "lot": main_coa.get("lot_number"),
        "purity_pct": results.get("purity_pct"),
        "net_content_mg": results.get("net_content_mg"),
        "heavy_metals": {k: hm.get(k) for k in ("pb_result", "as_result", "cd_result", "hg_result")} if hm else None,
        "analyzed_date": results.get("analyzed_date"),
        "pdf_url": main_coa.get("pdf_url"),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: KOVERA_SUPABASE_URL=... KOVERA_ANON_KEY=... python kovera.py <KVR-CODE>")
        sys.exit(1)
    import json
    print(json.dumps(verify_code(sys.argv[1]), indent=2))


if __name__ == "__main__":
    main()
