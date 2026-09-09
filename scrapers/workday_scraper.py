"""Workday board scraper — stub.

Workday boards are JS-heavy (client-rendered, often paginated via a "Load
more" button or infinite scroll) and vary more per-tenant than Greenhouse or
Lever. Do not implement until the Greenhouse pilot is validated end-to-end.
"""

from __future__ import annotations

from playwright.sync_api import Page

from scrapers.base_scraper import BaseScraper, ScrapedPosting


class WorkdayScraper(BaseScraper):
    ats_type = "workday"

    def list_postings(self, page: Page) -> list[ScrapedPosting]:
        raise NotImplementedError(
            "WorkdayScraper is not implemented yet — see scrapers/greenhouse_scraper.py "
            "for the reference pattern once the Greenhouse pilot is validated."
        )
