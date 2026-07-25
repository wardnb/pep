#!/usr/bin/env bash
# Start the Peptide Vendor Rater (API + frontend) on http://localhost:8000
set -e
cd "$(dirname "$0")"

# Optional: create/activate a virtualenv the first time
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi
source .venv/bin/activate

# Seed the database on first run (safe to re-run; it upserts).
python backend/seed.py

# Launch. Set DISABLE_SCHEDULER=1 to turn off the background scraper.
exec uvicorn app:app --app-dir backend --reload --host 0.0.0.0 --port 8000
