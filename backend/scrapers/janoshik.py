"""Janoshik COA verifier.

Janoshik Analytical is the community-standard third-party lab. Forged COAs are a
real problem, so the value here is *verification*, not listing: given the task
number + unique key printed on a COA (or a public.janoshik.com QR link), confirm
the report is genuine and read back the lab's own recorded purity/identity/date.

How Janoshik verification works (per janoshik.com/verification/):
  * Form: POST a `task number` + `unique key` to https://janoshik.com/verification/
  * Public DB / QR: https://public.janoshik.com resolves a scanned QR or test ID
The golden rule: the record must load on a janoshik.com / public.janoshik.com
domain — never a vendor-hosted page.

Usage:
    python backend/scrapers/janoshik.py <task_number> <unique_key>
or via the API:  POST /api/verify/janoshik  {"task_number": "...", "unique_key": "..."}
"""
from __future__ import annotations

import re
import sys
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

VERIFY_URL = "https://janoshik.com/verification/"
PUBLIC_BASE = "https://public.janoshik.com"


class JanoshikVerifier:
    def __init__(self, timeout: float = 20.0, user_agent: str = "peptide-rater/1.0"):
        self.timeout = timeout
        self.user_agent = user_agent

    def verify_coa(self, task_number: str, unique_key: str) -> dict:
        """Verify a COA. Returns a dict with authenticity + any parsed fields.

        This posts the credentials to the Janoshik verification form and parses
        the response. Network/parse failures return authentic=None (unknown)
        rather than raising, so callers can degrade gracefully.
        """
        result = {
            "task_number": task_number,
            "authentic": None,          # True / False / None(unknown)
            "compound": None,
            "purity_pct": None,
            "test_date": None,
            "verify_url": VERIFY_URL,
            "public_url": f"{PUBLIC_BASE}/?task={task_number}",
            "raw_excerpt": None,
            "error": None,
        }
        if httpx is None:
            result["error"] = "httpx not installed"
            return result
        try:
            resp = httpx.post(
                VERIFY_URL,
                data={"task": task_number, "key": unique_key,
                      "task_number": task_number, "unique_key": unique_key},
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout, follow_redirects=True,
            )
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"request failed: {exc}"
            return result

        low = text.lower()
        result["raw_excerpt"] = re.sub(r"\s+", " ", text)[:400]

        # Heuristic authenticity signals. The verification page shows the report
        # details on success and an error/"not found" message on failure.
        negative = any(w in low for w in
                       ("not found", "invalid", "no record", "does not exist", "incorrect"))
        positive = any(w in low for w in ("purity", "identity", "compound", "result", "verified"))
        if negative and not positive:
            result["authentic"] = False
        elif positive:
            result["authentic"] = True

        # Best-effort field extraction.
        m = re.search(r"purity[^0-9]{0,12}(\d{2,3}(?:\.\d+)?)\s*%", text, re.I)
        if m:
            result["purity_pct"] = float(m.group(1))
        m = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        if m:
            result["test_date"] = m.group(1)
        if BeautifulSoup is not None:
            try:
                soup = BeautifulSoup(text, "html.parser")
                cm = re.search(r"(?:compound|sample)[:\s]+([A-Za-z0-9\- ]{3,40})",
                               soup.get_text(" ", strip=True), re.I)
                if cm:
                    result["compound"] = cm.group(1).strip()
            except Exception:  # noqa: BLE001
                pass
        return result


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python janoshik.py <task_number> <unique_key>")
        sys.exit(1)
    v = JanoshikVerifier()
    out = v.verify_coa(sys.argv[1], sys.argv[2])
    print("Authentic:", out["authentic"])
    for k in ("compound", "purity_pct", "test_date", "public_url", "error"):
        if out.get(k) is not None:
            print(f"  {k}: {out[k]}")


if __name__ == "__main__":
    main()
