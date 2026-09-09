"""/approve, /reject, /mark-status endpoints.

Per PRD risk #3, email link-scanners can pre-fetch GET links and silently
"click" them. So:
  - GET  /respond/{token}  only *displays* a confirmation landing page
    (peek_token — does not consume the token or change any state).
  - POST /respond/confirm  is the only endpoint that actually consumes the
    token and changes state, and it only fires from a real button click on
    that landing page (not from a bare link).

Playwright automation is deliberately NOT run inline in the POST handler:
it needs a visible browser window in manual mode, which doesn't make sense
inside an async request/response cycle. Approval just flips the Application
status to APPROVED; actually driving the browser is a separate step (see
README "Run an approved application" for the CLI entrypoint), gated by
AUTO_SUBMIT_APPLICATIONS the same way either way.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.security import TokenError, peek_token, verify_and_consume_token
from database.db import session_scope
from database.models import Application, Job, JobStatus, TokenAction

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/respond/{raw_token:path}", response_class=HTMLResponse)
def show_confirmation(request: Request, raw_token: str):
    """Landing page — GET only ever reads/displays, never mutates state."""
    try:
        payload = peek_token(raw_token)
    except TokenError as exc:
        return templates.TemplateResponse(
            "approval_landing.html",
            {"request": request, "error": str(exc)},
            status_code=400,
        )

    with session_scope() as session:
        application = session.get(Application, payload["application_id"])
        if application is None:
            return templates.TemplateResponse(
                "approval_landing.html",
                {"request": request, "error": "Application not found."},
                status_code=404,
            )
        job = session.get(Job, application.job_id)
        context = {
            "request": request,
            "error": None,
            "raw_token": raw_token,
            "action": payload["action"],
            "company": job.company if job else "",
            "title": job.title if job else "",
        }
        return templates.TemplateResponse("approval_landing.html", context)


@router.post("/respond/confirm", response_class=HTMLResponse)
def confirm(request: Request, token: str = Form(...)):
    """The only state-changing step — must be reached via a real POST."""
    with session_scope() as session:
        try:
            token_row = verify_and_consume_token(session, token)
        except TokenError as exc:
            return templates.TemplateResponse(
                "approval_landing.html",
                {"request": request, "error": str(exc)},
                status_code=400,
            )

        application = session.get(Application, token_row.application_id)
        if application is None:
            return templates.TemplateResponse(
                "approval_landing.html",
                {"request": request, "error": "Application not found."},
                status_code=404,
            )

        if token_row.action == TokenAction.APPROVE:
            application.status = JobStatus.APPROVED
        else:
            application.status = JobStatus.REJECTED

        from datetime import datetime, timezone

        application.decided_at = datetime.now(timezone.utc)
        session.add(application)

        job = session.get(Job, application.job_id)
        context = {
            "request": request,
            "error": None,
            "confirmed": True,
            "action": token_row.action.value,
            "company": job.company if job else "",
            "title": job.title if job else "",
        }
        return templates.TemplateResponse("approval_landing.html", context)


@router.post("/mark-status")
def mark_status(application_id: str = Form(...), status: str = Form(...)):
    """Manual status override (e.g. INTERVIEWING) for statuses outside the
    approve/reject/auto-detected-closed lifecycle. Intended for local/manual
    use alongside the approval flow, not for exposure over a public tunnel.
    """
    if status not in JobStatus.__members__:
        return {"ok": False, "error": f"Unknown status: {status}"}

    with session_scope() as session:
        application = session.get(Application, application_id)
        if application is None:
            return {"ok": False, "error": "Application not found."}
        application.status = JobStatus[status]
        session.add(application)

    return {"ok": True}
