"""Build a static snapshot of the app for deployment to Cloudflare Pages
(or any static host).

It runs the same scoring/repository code the live API uses, writes the API
responses as static .json files, and emits an index.html wired to read them.
The result in ../dist/ is a fully browsable leaderboard — no server needed.
Dynamic-only features (manual refresh, the daily Reddit job, Janoshik verify)
require the live backend and are not part of the static build.

Usage:
    python backend/seed.py --reset      # make sure data is current
    python backend/build_static.py      # writes ../dist/
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from database import init_db
from repository import list_vendors
from seed import seed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST = PROJECT_ROOT / "dist"
FRONTEND = PROJECT_ROOT / "frontend" / "index.html"

# Injected into the static index.html so the frontend reads .json files
# relative to the page instead of calling the live /api backend.
CONFIG_SNIPPET = (
    '<script>window.APP_CONFIG={static:true,api:"api",ext:".json"};</script>'
)


def build() -> None:
    init_db()
    if not list_vendors():
        seed()

    # Import here so module import doesn't require a running server.
    import app as appmod

    if DIST.exists():
        shutil.rmtree(DIST)
    api = DIST / "api" / "vendors"
    api.mkdir(parents=True, exist_ok=True)
    api_root = DIST / "api"

    (api_root / "meta.json").write_text(json.dumps(appmod.meta()))
    (api_root / "labs.json").write_text(json.dumps(appmod.labs()))

    vendors = appmod.vendors()
    (api_root / "vendors.json").write_text(json.dumps(vendors))

    # One details map keyed by slug (avoids per-slug files with non-ASCII names
    # and keeps the static site to a handful of requests).
    details = {}
    for v in vendors:
        details[v["slug"]] = appmod.vendor_detail(v["slug"])
    (api_root / "details.json").write_text(json.dumps(details))

    # Emit index.html with the static config injected.
    html = FRONTEND.read_text()
    if "<!--APP_CONFIG-->" in html:
        html = html.replace("<!--APP_CONFIG-->", CONFIG_SNIPPET)
    else:  # fallback: inject before </head>
        html = html.replace("</head>", CONFIG_SNIPPET + "\n</head>", 1)
    (DIST / "index.html").write_text(html)

    # SPA-friendly 404 + a headers file (nice defaults for Pages).
    (DIST / "404.html").write_text(html)
    (DIST / "_headers").write_text(
        "/api/*\n  Cache-Control: public, max-age=300\n"
    )

    n_files = sum(1 for _ in DIST.rglob("*") if _.is_file())
    print(f"Built static site in {DIST} ({len(vendors)} vendors, {n_files} files)")


if __name__ == "__main__":
    build()
