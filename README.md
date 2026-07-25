# Peptide Vendor Rater

A small full-stack app that ranks research-peptide vendors by a **transparent,
weighted score** built from *public* third-party testing data. It ships seeded
with real, sourced data and can keep itself fresh with scheduled scrapers.

> **Disclaimer.** This tool rates the **transparency and public lab-testing** of
> vendors — it is not an endorsement of any vendor or of peptide use, and it is
> not medical advice. Vendor marketing purity claims are treated as *unverified*
> unless tied to a verifiable third-party COA. Unknown signals are left blank and
> excluded from the score rather than guessed at.

## What's in the box

```
peptide-rater/
├── backend/
│   ├── app.py           FastAPI app (API + serves the frontend)
│   ├── database.py      SQLite schema + connection (stdlib sqlite3, no ORM)
│   ├── repository.py    Data-access helpers (reads + upserts)
│   ├── scoring.py       The scoring engine (five weighted dimensions)
│   ├── seed.py          Loads data/seed_data.json into the DB
│   ├── ingest.py        Runs scrapers and persists their output
│   ├── scheduler.py     APScheduler job that re-scrapes on an interval
│   ├── test_scoring.py  Unit tests for the scoring engine
│   └── scrapers/        Pluggable scrapers (finnrick, peptigrity) + base/registry
├── data/
│   └── seed_data.json   Real, sourced seed dataset (47 vendors, 11 labs)
├── frontend/
│   └── index.html       Single-file UI: sortable leaderboard + detail panel
├── requirements.txt
└── run.sh               One command to install, seed, and launch
```

## Quick start

```bash
./run.sh
# then open http://localhost:8000
```

`run.sh` creates a virtualenv, installs dependencies, seeds the database, and
starts the server. To run it by hand instead:

```bash
pip install -r requirements.txt
python backend/seed.py --reset          # build/refresh data/peptides.db
uvicorn app:app --app-dir backend --reload
```

## How the score works

Each vendor gets a composite **0–100** score from five dimensions. Every
dimension is scored independently, and a vendor is **only** averaged over the
dimensions it actually has evidence for — a separate **confidence** value
(0–100%) reports how much of the intended weight was backed by data.

| Dimension | Default weight | Built from |
|---|---|---|
| Purity & dosage | 30% | HPLC purity %, fill/dose accuracy, aggregator pass-rate, external composite (e.g. Finnrick %) |
| Testing transparency | 18% | Publishes third-party COAs, uses an accredited lab, volume of public tests |
| Community reputation | 12% | Heuristic sentiment from public discussion (−1..+1), intentionally low-weighted |
| Test freshness | 12% | Recency of the most recent test (full credit < 6 months, zero at 3 years) |
| Sterility / endotoxin | 13% | Whether sterility/endotoxin panels were run and passed |
| Heavy metals (ICP-MS) | 15% | Whether ICP-MS heavy-metals panels (Pb/As/Cd/Hg) were run and within limits |

Weights live in `backend/scoring.py` (`DEFAULT_WEIGHTS`) — tune them freely; they
are renormalised automatically. Run the tests with:

```bash
python backend/test_scoring.py
```

### Two ranking modes

The leaderboard has a toggle:

- **Rank by score** — the raw weighted composite, with **confidence** shown
  alongside so a high score backed by little data is easy to spot.
- **Confidence-adjusted** — shrinks each score toward a neutral 50 in proportion
  to how little data backs it (`adjusted = total × confidence + 50 × (1 −
  confidence)`, in `scoring.py`). This demotes a flashy 93 backed by one signal
  below a solid 88 backed by full evidence — useful when you care about *how
  sure* the rating is, not just the headline number.

## Keeping data fresh (scrapers + scheduler)

Scrapers included, each reading only **public** pages:

- `finnrick` — per-vendor safety % + pass/fail counts (finnrick.com)
- `peptigrity` — per-vendor trust score + HPLC purity (peptigrity.com)
- `kold` — kold.us COA library (Accumark Labs COAs — the vendor that started this project)
- `reddit` — **daily Reddit researcher** (see below)

Run them on demand:

```bash
python backend/ingest.py                 # run all scrapers
python backend/ingest.py finnrick        # run one
curl -X POST http://localhost:8000/api/refresh   # trigger via API
```

When the server is running, a background job (APScheduler) re-runs all scrapers
every `SCRAPE_INTERVAL_HOURS` hours (default 24). Disable it with
`DISABLE_SCHEDULER=1`. Run the scheduler standalone with
`python backend/scheduler.py`.

### Daily Reddit researcher

The `reddit` scraper keeps tabs on the latest community chatter. On each daily
run it queries Reddit's public JSON search across r/Peptides, r/PeptideCycles,
and r/peptidesource for every vendor in the database, counts recent mentions,
applies a light positive/negative sentiment heuristic, and attaches the newest
post links as fresh sources — so the community dimension reflects what people
are saying *now*, not just the seed. It runs automatically as part of the daily
scheduler; run it alone with `python backend/ingest.py reddit`.

Notes: Reddit's public endpoints work for light unauthenticated use with a
descriptive User-Agent; if you hit rate limits, set `REDDIT_TOKEN` to an OAuth
bearer token. A live Reddit run overwrites the seeded community score/notes for
vendors it finds — re-run `python backend/seed.py` to restore the curated
values, or disable the reddit scraper in `scheduler.py`/`ingest.py` if you'd
rather keep the seed sentiment.

### Verifying a Janoshik COA

Janoshik is the community-standard lab, and forged COAs are a real problem. The
`JanoshikVerifier` confirms a COA is genuine from the **task number + unique
key** printed on it (or a public.janoshik.com QR link):

```bash
python backend/scrapers/janoshik.py <task_number> <unique_key>
# or via the API:
curl -X POST http://localhost:8000/api/verify/janoshik \
  -H 'Content-Type: application/json' \
  -d '{"task_number":"123456","unique_key":"abc..."}'
```

It posts to Janoshik's verification form and reports authentic true/false plus
any purity/date the lab has on record, degrading to `authentic: null` if the
site can't be reached (Janoshik may block automated requests from some hosts;
running locally from a browser-like context works best). Note KÖLD does **not**
use Janoshik — its COAs verify through Accumark Labs' own portal.

### Adding a scraper

Subclass `BaseScraper` in `backend/scrapers/`, set a `name`, implement
`scrape()` to return `VendorRecord` objects, decorate the class with
`@register`, and import it in `scrapers/__init__.py`. The ingest layer handles
all database writes, so scrapers stay pure fetch-and-parse.

> The bundled scrapers use best-effort HTML selectors that reflect each site's
> current public layout. If a site changes its markup, update the regex/selectors
> in that scraper — the parsing logic is small and commented. Always respect each
> site's robots.txt and terms of use, and keep request rates modest.

## API

| Endpoint | Description |
|---|---|
| `GET /api/vendors` | Ranked vendors with composite score, confidence, and per-dimension scores |
| `GET /api/vendors/{slug}` | Full detail: dimensions, published test data, sources |
| `GET /api/labs` | Testing labs and their accreditation |
| `GET /api/meta` | Weights and disclaimer |
| `POST /api/refresh` | Trigger a scraper refresh |
| `POST /api/verify/janoshik` | Verify a Janoshik COA by task number + unique key |

## Deploying to Cloudflare Pages (static snapshot)

Cloudflare Pages serves static files, so deployment publishes a **snapshot** of
the leaderboard — all vendors, scores, breakdowns, sources, filters, and both
ranking modes are fully browsable. The live-only features (manual refresh, the
daily Reddit job, Janoshik verify) need the Python backend and are not part of
the static build.

Build the snapshot:

```bash
python backend/seed.py --reset
python backend/build_static.py        # writes ./dist
```

Deploy it:

```bash
export CLOUDFLARE_API_TOKEN=xxxx      # token with "Cloudflare Pages: Edit"
export CLOUDFLARE_ACCOUNT_ID=xxxx     # from the Cloudflare dashboard
./deploy_cloudflare.sh                # builds + `wrangler pages deploy dist`
```

The site lands at `https://peptide-rater.pages.dev` (set `CF_PROJECT` to change
the name). Re-run `deploy_cloudflare.sh` any time to push a fresh snapshot after
updating the data. To keep the leaderboard live-updating instead of a snapshot,
host the FastAPI app on a Python host (Fly.io, Railway, Render, a VPS) and point
a Cloudflare DNS record at it — Pages alone can't run the backend.

## Data provenance & caveats

- The strongest independent structured source is **Finnrick** (9,000+ published
  tests across ~275 vendors); **Peptigrity** is a second open-methodology
  aggregator. Full COAs/lab names on Finnrick sit behind a paywall, so the seed
  uses only the public composite figures.
- **Finnrick exposes two different scales**: a 0–100 "safety %" on the vendor
  index and a 0–10 average on individual vendor pages. Only the 0–100 index
  value is stored as an aggregator composite (`agg_score`); where only the 0–10
  page average exists, `agg_score` is left null and the individual purity results
  are stored instead, rather than fabricating a conversion between the scales.
- Many "top vendor" listicles are **affiliate-conflicted** (discount codes,
  authors who co-own vendors). Seed rows sourced from those are flagged in each
  vendor's notes and their community scores are kept modest.
- Community reputation is a **heuristic**, not a measurement. Treat it as the
  softest signal — it is the lowest-weighted dimension by design.
- Labs differ in accreditation: Janoshik (the community favorite) is *not*
  ISO 17025 accredited; Vanguard, MZ Biolabs, and Colmaric are. Accreditation is
  stored per-lab and feeds the transparency dimension.
- **Finnrick is itself conflicted**: it earns revenue from vendors it rates
  (paid vendor tiers and testing), with no COI disclosure. Its scores are used
  as a *directional* signal only, and the disclaimer says so.

### Consumer vendors vs China raws suppliers

Vendors carry a `vendor_type`: `consumer` (retail brands) or `raws` (upstream
Chinese raw-material manufacturers). A filter in the UI isolates the `raws`
group, and each raws vendor shows a red badge, a direct-purchase risk warning,
and a **Sourcing** section. The honest finding from research is that the
"~2 suppliers, 40 resellers" upstream-consolidation pattern is real, but **no
citable source documents which specific Western brand sources from which
specific Chinese manufacturer** — so every brand↔manufacturer pairing is treated
as community-rumored, never asserted as fact. The raws entries (Guangzhou Jeep,
Nantong Guangyuan/GYC — flagged fraud, Wuhan Newtop, Qingdao Sigma/QSC, Heman,
Baohua Dongnuo, Noble Dragons) are included so you can see the upstream landscape
without implying a confirmed supply chain for any retail brand.

### Heavy metals (ICP-MS)

Only a handful of vendors publish real ICP-MS heavy-metals data. **Peptide
Partners** (Kovera Labs, actual Pb/As/Cd/Hg values) and **Life Link Research**
(Janoshik, USP <232>/<233> every batch) are the strongest; several others
(Peptidology, Imperial Peptides UK, Sports Technology Labs, BioLongevity) *claim*
heavy-metals screening but publish no numbers, so they get no heavy-metals credit
until numbers appear.

Data compiled 2026-07-25. Sources are attached per-vendor in the detail view.
