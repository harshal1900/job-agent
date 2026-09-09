"""Scraper for Greenhouse job boards (boards.greenhouse.io/<company>).

Greenhouse has shipped two board templates over the years:

- Current ("Job Boards" UI, live on most companies as of this writing):
  postings render as `<a href=".../jobs/<id>">` containing two `<p>` tags —
  `.body--medium` (title) and `.body__secondary.body--metadata` (location).
  Verified live against gitlab/stripe/figma/discord's boards.
- Classic (older, some boards may still serve it): `div.opening` anchors
  under `.level-0`/`.level-1` section headers.

We try the current template first and fall back to the classic one, since
which template a given company's board serves isn't predictable from the
URL alone.
"""

from __future__ import annotations

from urllib.parse import urljoin

from playwright.sync_api import Page

from scrapers.base_scraper import BaseScraper, ScrapedPosting


class GreenhouseScraper(BaseScraper):
    ats_type = "greenhouse"

    def list_postings(self, page: Page) -> list[ScrapedPosting]:
        postings = self._list_postings_current_template(page)
        if postings:
            return postings
        return self._list_postings_classic_template(page)

    def _list_postings_current_template(self, page: Page) -> list[ScrapedPosting]:
        postings: list[ScrapedPosting] = []

        links = page.locator("a[href*='/jobs/']")
        count = links.count()

        for i in range(count):
            link = links.nth(i)
            href = link.get_attribute("href") or ""
            if not href:
                continue
            source_url = urljoin(self.board_url, href)

            title_el = link.locator("p.body--medium")
            title = title_el.first.inner_text().strip() if title_el.count() > 0 else ""

            location_el = link.locator("p.body__secondary")
            location = (
                location_el.first.inner_text().strip() if location_el.count() > 0 else ""
            )

            if not title:
                continue

            postings.append(
                ScrapedPosting(
                    company=self.company,
                    title=title,
                    location=location,
                    source_url=source_url,
                )
            )

        return postings

    def _list_postings_classic_template(self, page: Page) -> list[ScrapedPosting]:
        postings: list[ScrapedPosting] = []

        openings = page.locator("div.opening")
        count = openings.count()

        for i in range(count):
            opening = openings.nth(i)
            link = opening.locator("a").first
            title = link.inner_text().strip()
            href = link.get_attribute("href") or ""
            source_url = urljoin(self.board_url, href)

            location = ""
            location_el = opening.locator(".location")
            if location_el.count() > 0:
                location = location_el.first.inner_text().strip()

            if not title or not source_url:
                continue

            postings.append(
                ScrapedPosting(
                    company=self.company,
                    title=title,
                    location=location,
                    source_url=source_url,
                )
            )

        return postings

    def fetch_description(self, page: Page, posting_url: str) -> str:
        """Load a single posting page and return its full description text."""
        self.goto(page, posting_url)
        for selector in (".job__description", "#content"):
            content = page.locator(selector)
            if content.count() > 0:
                return content.first.inner_text().strip()
        return page.locator("body").inner_text().strip()
