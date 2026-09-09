from __future__ import annotations

from scrapers import base_scraper
from scrapers.base_scraper import BaseScraper, ScrapedPosting


class _FakePage:
    pass


class _FakeBrowser:
    def new_context(self, user_agent):
        return self

    def new_page(self):
        return _FakePage()

    def close(self):
        pass


class _FakePlaywright:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def chromium(self):
        return self

    def launch(self, headless):
        return _FakeBrowser()


class _FakeScraper(BaseScraper):
    """A scraper stand-in that skips real navigation/throttling entirely so
    these tests don't launch a browser or sleep."""

    ats_type = "fake"

    def __init__(self, postings, fail_urls=()):
        super().__init__(company="acme", board_url="https://example.com")
        self._postings = postings
        self._fail_urls = set(fail_urls)

    def goto(self, page, url):
        pass

    def list_postings(self, page):
        return self._postings

    def fetch_description(self, page, posting_url):
        if posting_url in self._fail_urls:
            raise RuntimeError("boom")
        return f"description for {posting_url}"


def _postings():
    return [
        ScrapedPosting(company="acme", title="A", location="", source_url="https://x/1"),
        ScrapedPosting(company="acme", title="B", location="", source_url="https://x/2"),
    ]


def test_run_fetches_description_for_every_posting(monkeypatch):
    # This is the regression test for the real bug: fetch_description()
    # existed on GreenhouseScraper but nothing in run() ever called it, so
    # description_raw was empty for every posting ever scraped.
    monkeypatch.setattr(base_scraper, "sync_playwright", lambda: _FakePlaywright())
    scraper = _FakeScraper(_postings())

    result = scraper.run()

    assert result[0].description_raw == "description for https://x/1"
    assert result[1].description_raw == "description for https://x/2"


def test_run_leaves_description_empty_and_continues_after_one_fetch_failure(
    monkeypatch,
):
    monkeypatch.setattr(base_scraper, "sync_playwright", lambda: _FakePlaywright())
    scraper = _FakeScraper(_postings(), fail_urls={"https://x/1"})

    result = scraper.run()

    assert result[0].description_raw == ""
    assert result[1].description_raw == "description for https://x/2"


class _MinimalScraper(BaseScraper):
    """A scraper that only implements the required abstract method, to
    exercise BaseScraper's default fetch_description()."""

    ats_type = "minimal"

    def list_postings(self, page):
        return []


def test_default_fetch_description_is_empty_string_not_a_crash():
    # A scraper subclass that hasn't implemented per-posting fetching yet
    # (e.g. a future Lever/Workday scraper) must degrade gracefully, since
    # api/scheduler.py's `job.description_raw or job.title` fallback
    # depends on this being a plain empty string rather than raising.
    scraper = _MinimalScraper(company="acme", board_url="https://example.com")
    assert scraper.fetch_description(page=None, posting_url="https://x/1") == ""
