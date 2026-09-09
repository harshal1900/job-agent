"""APScheduler job registration: discovery/scan cycle + 24h status checks."""

from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from jinja2 import Environment, FileSystemLoader

from api.security import issue_token
from automation.status_checker import check_job_statuses
from config.settings import BASE_DIR, get_settings
from database.db import session_scope
from database.models import Application, ATSType, Job, JobStatus, TokenAction
from llm.match_scorer import MatchScorer
from llm.resume_rewriter import HallucinationError, ResumeRewriter
from scrapers.greenhouse_scraper import GreenhouseScraper

logger = logging.getLogger(__name__)

TEMPLATES_DIR = BASE_DIR / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

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


def _send_email(subject: str, html_body: str) -> None:
    settings = get_settings()
    if not (settings.SMTP_USER and settings.SMTP_APP_PASSWORD and settings.EMAIL_TO):
        logger.warning("Email not configured — skipping send: %s", subject)
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    message["To"] = settings.EMAIL_TO
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_APP_PASSWORD)
        server.send_message(message)


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

                try:
                    match = scorer.score(profile, job.description_raw or job.title)
                    job.match_score = match.match_score
                    job.keyword_gaps = json.dumps(match.keyword_gaps)
                    job.status = JobStatus.SCORED

                    rewrite = rewriter.rewrite(
                        profile, job.description_raw or job.title, strict=True
                    )
                except HallucinationError:
                    logger.warning(
                        "Skipping %s — tailored draft failed the anti-hallucination "
                        "guardrail; needs manual tailoring instead of auto-email.",
                        job.source_url,
                    )
                    continue
                except Exception:
                    logger.exception("Scoring/tailoring failed for %s", job.source_url)
                    continue

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

                template = _jinja_env.get_template("email_match.html")
                html = template.render(
                    company=job.company,
                    title=job.title,
                    match_score=job.match_score,
                    keyword_gaps=match.keyword_gaps,
                    resume_bullets=rewrite.resume_bullets,
                    cover_letter_paragraph=rewrite.cover_letter_paragraph,
                    approve_url=f"{settings.PUBLIC_BASE_URL}/respond/{approve_token.raw_token}",
                    reject_url=f"{settings.PUBLIC_BASE_URL}/respond/{reject_token.raw_token}",
                )
                _send_email(f"New match: {job.title} @ {job.company}", html)


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
