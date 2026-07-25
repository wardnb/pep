"""Background scheduler that periodically re-runs scrapers to refresh data.

Uses APScheduler. Started automatically by the FastAPI app (see app.py) unless
disabled via the DISABLE_SCHEDULER env var. Can also be run standalone:

    python backend/scheduler.py
"""
from __future__ import annotations

import os

from ingest import run_all

# How often to refresh, in hours (override with SCRAPE_INTERVAL_HOURS).
DEFAULT_INTERVAL_HOURS = float(os.environ.get("SCRAPE_INTERVAL_HOURS", "24"))


def refresh_job() -> None:
    print("[scheduler] running scheduled data refresh...")
    summary = run_all()
    print(f"[scheduler] refresh complete: {summary}")


def build_scheduler(interval_hours: float = DEFAULT_INTERVAL_HOURS):
    """Return a configured (but not started) BackgroundScheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        refresh_job,
        trigger="interval",
        hours=interval_hours,
        id="peptide_refresh",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


if __name__ == "__main__":
    import time

    from apscheduler.schedulers.blocking import BlockingScheduler

    sched = BlockingScheduler()
    sched.add_job(refresh_job, "interval", hours=DEFAULT_INTERVAL_HOURS,
                  id="peptide_refresh", next_run_time=None)
    print(f"[scheduler] refreshing every {DEFAULT_INTERVAL_HOURS}h. Ctrl-C to stop.")
    # Run once immediately, then on the interval.
    refresh_job()
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[scheduler] stopped.")
