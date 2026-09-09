"""24h job-close/expiry checker, registered as an APScheduler job.

Revisits every job not already CLOSED/EXPIRED and looks for closure signals
(404/410, or ATS-specific "no longer accepting applications" text). Uses a
plain httpx GET per posting (not a full Playwright browser) since we only
need page text, and throttles between requests per PRD risk #4: hitting the
same URLs on a schedule at scale can look like scraping abuse, so keep
volume low and space requests out.
"""

from __future__ import annotations

import logging
import time

import httpx

from config.settings import get_settings
from database.db import session_scope
from database.models import Job, JobStatus

logger = logging.getLogger(__name__)

_CLOSED_MARKERS = (
    "no longer accepting applications",
    "this job is no longer available",
    "position has been filled",
    "posting has closed",
    "job not found",
)


def _looks_closed(status_code: int, body_text: str) -> bool:
    if status_code in (404, 410):
        return True
    lowered = body_text.lower()
    return any(marker in lowered for marker in _CLOSED_MARKERS)


def check_job_statuses() -> dict[str, int]:
    """Run one pass over all open jobs; return counts for logging/summary."""
    settings = get_settings()
    checked = 0
    newly_closed = 0

    with session_scope() as session:
        open_jobs = (
            session.query(Job)
            .filter(Job.status.notin_([JobStatus.CLOSED, JobStatus.EXPIRED]))
            .all()
        )

        with httpx.Client(
            headers={"User-Agent": settings.SCRAPER_USER_AGENT}, timeout=30.0
        ) as client:
            for job in open_jobs:
                try:
                    response = client.get(job.source_url, follow_redirects=True)
                    closed = _looks_closed(response.status_code, response.text)
                except httpx.HTTPError as exc:
                    logger.warning("Status check failed for %s: %s", job.source_url, exc)
                    closed = False

                job.last_checked_at = _utcnow()
                if closed:
                    job.status = JobStatus.CLOSED
                    job.closed_at = _utcnow()
                    newly_closed += 1

                checked += 1
                time.sleep(settings.SCRAPER_MIN_DELAY_SECONDS)

    logger.info("Status check complete: %d checked, %d newly closed", checked, newly_closed)
    return {"checked": checked, "newly_closed": newly_closed}


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
