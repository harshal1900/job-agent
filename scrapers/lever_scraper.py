"""Lever board scraper — stub.

Per PRD build order: get greenhouse_scraper.py working end-to-end first.
Implement list_postings() following the same pattern once that pilot run
succeeds (Lever boards at jobs.lever.co/<company> use `.posting` cards).
"""

from __future__ import annotations

from playwright.sync_api import Page

from scrapers.base_scraper import BaseScraper, ScrapedPosting


class LeverScraper(BaseScraper):
    ats_type = "lever"

    def list_postings(self, page: Page) -> list[ScrapedPosting]:
        raise NotImplementedError(
            "LeverScraper is not implemented yet — see scrapers/greenhouse_scraper.py "
            "for the reference pattern once the Greenhouse pilot is validated."
        )
