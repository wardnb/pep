"""Scraper package. Importing it registers all bundled scrapers."""
from .base import (  # noqa: F401
    BaseScraper, VendorRecord, available_scrapers, get_scraper, register,
)
from . import finnrick  # noqa: F401  (registers FinnrickScraper)
from . import peptigrity  # noqa: F401  (registers PeptigrityScraper)
from . import kold  # noqa: F401  (registers KoldScraper)
from . import reddit  # noqa: F401  (registers RedditScraper)
from .janoshik import JanoshikVerifier  # noqa: F401  (verifier, not a bulk scraper)
