"""Email notifications via the Resend API.

Replaces the old Gmail SMTP path entirely — Resend's HTTP API needs no app
password or SMTP session handling, just RESEND_API_KEY.

Note: EMAIL_FROM is expected to be Resend's shared test domain
(onboarding@resend.dev) for this project, which can only deliver to the
Resend account owner's own address — EMAIL_TO is that same address here.
That's expected and fine since this only ever emails one person; it is not
something to work around (e.g. don't suggest domain verification).
"""

from __future__ import annotations

import logging

import resend
from jinja2 import Environment, FileSystemLoader

from config.settings import BASE_DIR, get_settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = BASE_DIR / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def send_email(subject: str, html_body: str) -> str | None:
    """Low-level send via Resend. Returns the sent email's id, or None if
    email isn't configured (logged, not raised, so a scan cycle can't be
    taken down by a missing API key)."""
    settings = get_settings()
    if not (settings.RESEND_API_KEY and settings.EMAIL_TO):
        logger.warning("Email not configured — skipping send: %s", subject)
        return None

    resend.api_key = settings.RESEND_API_KEY
    response = resend.Emails.send(
        {
            "from": settings.EMAIL_FROM,
            "to": [settings.EMAIL_TO],
            "subject": subject,
            "html": html_body,
        }
    )
    email_id = response.get("id") if isinstance(response, dict) else None
    logger.info("Sent email via Resend: %r (id=%s)", subject, email_id)
    return email_id


def send_match_email(
    *,
    company: str,
    title: str,
    match_score: float,
    keyword_gaps: list[str],
    resume_bullets: list[str],
    cover_letter_paragraph: str,
    approve_url: str,
    reject_url: str,
) -> str | None:
    template = _jinja_env.get_template("email_match.html")
    html = template.render(
        company=company,
        title=title,
        match_score=match_score,
        keyword_gaps=keyword_gaps,
        resume_bullets=resume_bullets,
        cover_letter_paragraph=cover_letter_paragraph,
        approve_url=approve_url,
        reject_url=reject_url,
    )
    return send_email(f"New match: {title} @ {company}", html)


def send_prep_email(
    *, company: str, title: str, star_questions: list[dict], study_topics: list[dict]
) -> str | None:
    template = _jinja_env.get_template("email_prep_package.html")
    html = template.render(
        company=company,
        title=title,
        star_questions=star_questions,
        study_topics=study_topics,
    )
    return send_email(f"Interview prep: {title} @ {company}", html)
