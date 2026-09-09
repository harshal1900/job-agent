"""Shared scraper contract + politeness helpers.

Every ATS scraper subclasses BaseScraper and implements list_postings().
Rate limiting and a descriptive User-Agent are enforced here, not left to
each subclass, so we don't accidentally hammer a career board.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from playwright.sync_api import Browser, Page, sync_playwright

from config.settings import get_settings


@dataclass
class ScrapedPosting:
    company: str
    title: str
    location: str
    source_url: str
    description_raw: str = ""


class BaseScraper(ABC):
    ats_type: str = "base"

    def __init__(self, company: str, board_url: str):
        self.company = company
        self.board_url = board_url
        self.settings = get_settings()
        self._last_request_at: float = 0.0

    def _throttle(self) -> None:
        min_delay = self.settings.SCRAPER_MIN_DELAY_SECONDS
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)
        self._last_request_at = time.monotonic()

    def new_page(self, browser: Browser) -> Page:
        context = browser.new_context(user_agent=self.settings.SCRAPER_USER_AGENT)
        return context.new_page()

    def goto(self, page: Page, url: str) -> None:
        self._throttle()
        page.goto(url, wait_until="domcontentloaded")

    @abstractmethod
    def list_postings(self, page: Page) -> list[ScrapedPosting]:
        """Return all open postings currently visible on the board page."""
        raise NotImplementedError

    def run(self) -> list[ScrapedPosting]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = self.new_page(browser)
                self.goto(page, self.board_url)
                return self.list_postings(page)
            finally:
                browser.close()
