"""APScheduler job registration: discovery/scan cycle + 24h status checks."""

from __future__ import annotations

import json
import logging

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright

from api.emailer import send_match_email
from api.security import issue_token
from automation.status_checker import check_job_statuses
from config.settings import BASE_DIR, get_settings
from database.db import session_scope
from database.models import Application, ATSType, Job, JobStatus, TokenAction
from llm.match_scorer import MatchScorer
from llm.resume_rewriter import HallucinationError, ResumeRewriter
from scrapers.greenhouse_scraper import GreenhouseScraper

logger = logging.getLogger(__name__)

# Only ATSes with an implemented scraper participate in the scan cycle —
# lever/workday raise NotImplementedError today (see scrapers/), so boards
# targeting them are just skipped with a log line, not a crash.
_SCRAPERS = {
    "greenhouse": GreenhouseScraper,
}


def _load_profile() -> dict:
    with open(BASE_DIR / "config" / "master_profile.json") as f:
        return json.load(f)


def _load_target_boards() -> list[dict]:
    with open(BASE_DIR / "config" / "target_boards.yaml") as f:
        data = yaml.safe_load(f) or {}
    return [b for b in data.get("boards", []) if b.get("enabled")]


def _needs_scoring(job: Job) -> bool:
    return job.match_score is None


def _needs_tailoring(job: Job, session, settings) -> bool:
    if job.match_score is None or job.match_score < settings.MATCH_SCORE_THRESHOLD:
        return False
    existing_app = (
        session.query(Application).filter(Application.job_id == job.id).first()
    )
    return existing_app is None


def _score_and_tailor(
    session,
    job: Job,
    profile: dict,
    scorer: MatchScorer,
    rewriter: ResumeRewriter,
    settings,
) -> None:
    """Score `job` if it doesn't have a score yet, then tailor + email it if
    it scores at/above threshold and doesn't already have an Application.
    Shared by scan_job() (brand-new postings) and retry_pending_jobs()
    (existing postings that failed scoring or tailoring last time) so a
    retry never re-scrapes and never redoes work that already succeeded.
    """
    if _needs_scoring(job):
        try:
            match_score_result = scorer.score(profile, job.description_raw or job.title)
            job.match_score = match_score_result.match_score
            job.keyword_gaps = json.dumps(match_score_result.keyword_gaps)
            job.status = JobStatus.SCORED
            session.flush()
        except Exception:
            logger.exception("Scoring failed for %s", job.source_url)
            return
        keyword_gaps = match_score_result.keyword_gaps
    else:
        keyword_gaps = json.loads(job.keyword_gaps or "[]")

    if job.match_score < settings.MATCH_SCORE_THRESHOLD:
        logger.info(
            "%s scored %d (below MATCH_SCORE_THRESHOLD=%d) — leaving at SCORED, "
            "no tailoring/email.",
            job.source_url,
            job.match_score,
            settings.MATCH_SCORE_THRESHOLD,
        )
        return

    if not _needs_tailoring(job, session, settings):
        return

    try:
        rewrite = rewriter.rewrite(profile, job.description_raw or job.title, strict=True)
    except HallucinationError as exc:
        # str(exc) carries the actual flagged terms (see HallucinationError's
        # raise site in resume_rewriter.py) -- log it, not just the fact that
        # it happened, so a real catch vs. a false-positive pattern can
        # actually be told apart after the fact instead of needing a fresh,
        # possibly non-reproducing regeneration to find out.
        logger.warning(
            "Skipping %s — tailored draft failed the anti-hallucination guardrail "
            "(%s); needs manual tailoring instead of auto-email.",
            job.source_url,
            exc,
        )
        return
    except Exception:
        logger.exception("Tailoring failed for %s", job.source_url)
        return

    application = Application(
        job_id=job.id,
        resume_draft="\n".join(rewrite.resume_bullets),
        cover_letter_draft=rewrite.cover_letter_paragraph,
        status=JobStatus.PENDING_APPROVAL,
    )
    session.add(application)
    job.status = JobStatus.PENDING_APPROVAL
    session.flush()

    approve_token = issue_token(session, application.id, TokenAction.APPROVE)
    reject_token = issue_token(session, application.id, TokenAction.REJECT)

    send_match_email(
        company=job.company,
        title=job.title,
        match_score=job.match_score,
        keyword_gaps=keyword_gaps,
        resume_bullets=rewrite.resume_bullets,
        cover_letter_paragraph=rewrite.cover_letter_paragraph,
        approve_url=f"{settings.PUBLIC_BASE_URL}/respond/{approve_token.raw_token}",
        reject_url=f"{settings.PUBLIC_BASE_URL}/respond/{reject_token.raw_token}",
    )


def scan_job() -> None:
    """One discovery -> score -> tailor -> save -> email cycle."""
    settings = get_settings()
    profile = _load_profile()
    scorer = MatchScorer()
    rewriter = ResumeRewriter()

    for board in _load_target_boards():
        ats = board["ats"]
        scraper_cls = _SCRAPERS.get(ats)
        if scraper_cls is None:
            logger.info(
                "Skipping %s (%s) — scraper not implemented yet", board["company"], ats
            )
            continue

        scraper = scraper_cls(company=board["company"], board_url=board["url"])
        try:
            postings = scraper.run()
        except Exception:
            logger.exception("Scrape failed for %s", board["company"])
            continue

        with session_scope() as session:
            for posting in postings:
                existing = (
                    session.query(Job)
                    .filter(Job.source_url == posting.source_url)
                    .one_or_none()
                )
                if existing is not None:
                    continue

                job = Job(
                    company=posting.company,
                    title=posting.title,
                    location=posting.location,
                    ats_type=ATSType(ats),
                    source_url=posting.source_url,
                    description_raw=posting.description_raw,
                    status=JobStatus.NEW,
                )
                session.add(job)
                session.flush()

                _score_and_tailor(session, job, profile, scorer, rewriter, settings)


def retry_pending_jobs() -> dict:
    """Re-attempt scoring/tailoring for jobs already in the DB that either
    never got a real score (a transient failure last time — rate limit,
    malformed LLM output) or scored at/above threshold but never got a
    successfully tailored Application. Does NOT re-scrape — uses the
    description_raw already stored from the original scan. Use this after
    fixing a transient failure or waiting out a rate limit, instead of
    re-running scan_job() (which only looks at brand-new postings anyway —
    it skips any source_url already in the DB, success or failure).
    """
    settings = get_settings()
    profile = _load_profile()
    scorer = MatchScorer()
    rewriter = ResumeRewriter()

    scored_now = 0
    tailored_now = 0

    with session_scope() as session:
        candidates = (
            session.query(Job)
            .filter(
                Job.status.notin_(
                    [JobStatus.CLOSED, JobStatus.EXPIRED, JobStatus.REJECTED]
                )
            )
            .all()
        )
        for job in candidates:
            needs_score = _needs_scoring(job)
            # _needs_tailoring() requires job.match_score >= threshold, which
            # is unknowable before an unscored job is actually scored — so
            # this pre-check alone would always read False for a job that
            # gets scored AND tailored in the same pass below, undercounting
            # tailored_now even though the tailor+email genuinely happened.
            # Track "had an Application before" instead and diff after.
            if not (needs_score or _needs_tailoring(job, session, settings)):
                continue
            had_application = _has_application(session, job)

            _score_and_tailor(session, job, profile, scorer, rewriter, settings)

            if needs_score and job.match_score is not None:
                scored_now += 1
            if not had_application and _has_application(session, job):
                tailored_now += 1

    return {"scored_now": scored_now, "tailored_now": tailored_now}


def _has_application(session, job: Job) -> bool:
    return (
        session.query(Application).filter(Application.job_id == job.id).first()
        is not None
    )


def backfill_descriptions() -> dict:
    """One-time repair for a real bug: GreenhouseScraper.fetch_description()
    was implemented but never called anywhere in the scan pipeline, so
    description_raw has been empty for every job ever scraped — matching
    and tailoring have only ever seen the bare job title, not real JD text.

    Re-fetches real descriptions for every job still on the empty fallback,
    resets each to NEW (clearing match_score/keyword_gaps) so
    retry_pending_jobs() naturally re-scores/re-tailors it with real
    content, and deletes any existing Application (cascading its approval
    tokens) built from the wrong text — otherwise _needs_tailoring() would
    see "already has an Application" and silently keep the stale, wrong
    draft forever even after the job re-qualifies.
    """
    boards_by_company = {b["company"]: b for b in _load_target_boards()}
    updated = 0
    failed = 0

    with session_scope() as session:
        jobs = (
            session.query(Job)
            .filter((Job.description_raw == None) | (Job.description_raw == ""))  # noqa: E711
            .all()
        )
        by_company: dict[str, list[Job]] = {}
        for job in jobs:
            by_company.setdefault(job.company, []).append(job)

        for company, company_jobs in by_company.items():
            board = boards_by_company.get(company)
            ats = (
                company_jobs[0].ats_type.value
                if hasattr(company_jobs[0].ats_type, "value")
                else company_jobs[0].ats_type
            )
            scraper_cls = _SCRAPERS.get(ats)
            if scraper_cls is None or board is None:
                logger.warning(
                    "No scraper/board config for %s (%s) — skipping %d jobs",
                    company,
                    ats,
                    len(company_jobs),
                )
                failed += len(company_jobs)
                continue

            scraper = scraper_cls(company=company, board_url=board["url"])
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = scraper.new_page(browser)
                    for job in company_jobs:
                        try:
                            description = scraper.fetch_description(page, job.source_url)
                        except Exception:
                            logger.exception(
                                "Failed to backfill description for %s", job.source_url
                            )
                            failed += 1
                            continue

                        job.description_raw = description
                        job.match_score = None
                        job.keyword_gaps = ""
                        job.status = JobStatus.NEW

                        existing_app = (
                            session.query(Application)
                            .filter(Application.job_id == job.id)
                            .first()
                        )
                        if existing_app is not None:
                            session.delete(existing_app)

                        session.flush()
                        updated += 1
                finally:
                    browser.close()

    return {"updated": updated, "failed": failed}


def register_jobs(scheduler: BackgroundScheduler) -> None:
    scheduler.add_job(scan_job, "interval", hours=6, id="scan_job", replace_existing=True)
    scheduler.add_job(
        check_job_statuses,
        "interval",
        hours=24,
        id="status_check_job",
        replace_existing=True,
    )


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    register_jobs(scheduler)
    scheduler.start()
    return scheduler
