from __future__ import annotations

import time

import pytest

from api.security import TokenError, issue_token, peek_token, verify_and_consume_token
from database.models import Application, Job, TokenAction


def _make_application(db_session) -> Application:
    job = Job(
        company="Acme",
        title="Engineer",
        ats_type="greenhouse",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    db_session.add(job)
    db_session.flush()

    application = Application(job_id=job.id)
    db_session.add(application)
    db_session.flush()
    return application


def test_issue_and_consume_token_succeeds_once(db_session):
    application = _make_application(db_session)

    issued = issue_token(db_session, application.id, TokenAction.APPROVE)
    row = verify_and_consume_token(db_session, issued.raw_token)

    assert row.application_id == application.id
    assert row.is_used

    with pytest.raises(TokenError):
        verify_and_consume_token(db_session, issued.raw_token)


def test_peek_token_does_not_consume(db_session):
    application = _make_application(db_session)
    issued = issue_token(db_session, application.id, TokenAction.REJECT)

    payload = peek_token(issued.raw_token)
    assert payload["application_id"] == application.id
    assert payload["action"] == "reject"

    # peeking twice, then consuming once, should still work
    peek_token(issued.raw_token)
    row = verify_and_consume_token(db_session, issued.raw_token)
    assert row.is_used


def test_tampered_token_rejected(db_session):
    application = _make_application(db_session)
    issued = issue_token(db_session, application.id, TokenAction.APPROVE)
    tampered = issued.raw_token[:-1] + ("a" if issued.raw_token[-1] != "a" else "b")

    with pytest.raises(TokenError):
        verify_and_consume_token(db_session, tampered)


def test_expired_token_rejected(db_session, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("APPROVAL_TOKEN_TTL_SECONDS", "1")
    get_settings.cache_clear()

    application = _make_application(db_session)
    issued = issue_token(db_session, application.id, TokenAction.APPROVE)

    time.sleep(1.5)

    with pytest.raises(TokenError):
        verify_and_consume_token(db_session, issued.raw_token)

    get_settings.cache_clear()
