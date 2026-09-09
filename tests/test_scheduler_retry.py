from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

from api import scheduler as scheduler_module
from database.models import Application, ATSType, Job, JobStatus


class FakeScorer:
    """Looks up a canned (score, keyword_gaps) result by the description
    string passed in — tests set each job's description_raw to a unique
    marker so this can tell jobs apart without touching real LLM code."""

    def __init__(self, results: dict[str, tuple[int, list[str]]]):
        self.results = results
        self.calls: list[str] = []

    def score(self, profile, description):
        self.calls.append(description)
        score, gaps = self.results[description]
        return _FakeMatchResult(score, gaps, "fake rationale")


@dataclass
class _FakeMatchResult:
    match_score: int
    keyword_gaps: list[str]
    rationale: str


class FakeRewriter:
    def __init__(self):
        self.calls: list[str] = []

    def rewrite(self, profile, description, strict=True):
        self.calls.append(description)
        return _FakeRewriteResult(
            resume_bullets=["Did a real thing"],
            cover_letter_paragraph="Real cover letter.",
        )


@dataclass
class _FakeRewriteResult:
    resume_bullets: list[str]
    cover_letter_paragraph: str
    unsupported_terms: list = field(default_factory=list)


@pytest.fixture
def scheduler_env(monkeypatch, db_session):
    """Wires api.scheduler's session_scope/MatchScorer/ResumeRewriter/email
    to the in-memory test DB and fakes, so retry_pending_jobs() can run
    without touching the real DB, a real LLM, or Resend."""

    @contextmanager
    def fake_session_scope():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(scheduler_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(scheduler_module, "_load_profile", lambda: {"skills": ["Python"]})

    sent_emails = []
    monkeypatch.setattr(
        scheduler_module,
        "send_match_email",
        lambda **kwargs: sent_emails.append(kwargs),
    )

    return {"session": db_session, "sent_emails": sent_emails}


def _make_job(session, *, description, match_score=None, keyword_gaps=None, status=JobStatus.NEW):
    job = Job(
        company="Acme",
        title=description,
        ats_type=ATSType.GREENHOUSE,
        source_url=f"https://boards.greenhouse.io/acme/jobs/{description}",
        description_raw=description,
        match_score=match_score,
        keyword_gaps=json.dumps(keyword_gaps or []),
        status=status,
    )
    session.add(job)
    session.flush()
    return job


def test_retry_scores_previously_unscored_job(monkeypatch, scheduler_env):
    session = scheduler_env["session"]
    job = _make_job(session, description="JOB_UNSCORED")

    scorer = FakeScorer({"JOB_UNSCORED": (40, ["Kubernetes"])})
    monkeypatch.setattr(scheduler_module, "MatchScorer", lambda: scorer)
    monkeypatch.setattr(scheduler_module, "ResumeRewriter", lambda: FakeRewriter())

    result = scheduler_module.retry_pending_jobs()

    assert result["scored_now"] == 1
    assert result["tailored_now"] == 0
    assert job.match_score == 40
    assert scorer.calls == ["JOB_UNSCORED"]
    assert scheduler_env["sent_emails"] == []


def test_retry_counts_tailored_now_for_job_scored_and_tailored_in_same_pass(
    monkeypatch, scheduler_env
):
    """Regression test for a real reporting bug: _needs_tailoring() requires
    match_score >= threshold, which is unknowable for a job that starts
    unscored -- so a job that gets scored above threshold AND tailored +
    emailed in this same retry pass was silently missing from tailored_now
    even though the email genuinely went out (confirmed against Resend logs
    in production: 11 real emails sent, 'tailored_now' reported 0)."""
    session = scheduler_env["session"]
    job = _make_job(session, description="JOB_UNSCORED_BUT_QUALIFIES")

    scorer = FakeScorer({"JOB_UNSCORED_BUT_QUALIFIES": (85, [])})
    monkeypatch.setattr(scheduler_module, "MatchScorer", lambda: scorer)
    monkeypatch.setattr(scheduler_module, "ResumeRewriter", lambda: FakeRewriter())

    result = scheduler_module.retry_pending_jobs()

    assert result["scored_now"] == 1
    assert result["tailored_now"] == 1
    apps = session.query(Application).filter(Application.job_id == job.id).all()
    assert len(apps) == 1
    assert len(scheduler_env["sent_emails"]) == 1


def test_retry_tailors_scored_job_with_no_application(monkeypatch, scheduler_env):
    """Regression test for the exact real-world case: a job already scored
    above threshold (from a prior run) but whose tailoring step failed and
    left it with zero Application rows — retry must pick it up without
    re-scoring."""
    session = scheduler_env["session"]
    job = _make_job(
        session,
        description="JOB_SCORED_NO_APP",
        match_score=78,
        keyword_gaps=["Logistics"],
        status=JobStatus.SCORED,
    )

    scorer = FakeScorer({})  # score() must NOT be called
    monkeypatch.setattr(scheduler_module, "MatchScorer", lambda: scorer)
    monkeypatch.setattr(scheduler_module, "ResumeRewriter", lambda: FakeRewriter())

    result = scheduler_module.retry_pending_jobs()

    assert result["scored_now"] == 0
    assert result["tailored_now"] == 1
    assert scorer.calls == []  # never re-scored
    apps = session.query(Application).filter(Application.job_id == job.id).all()
    assert len(apps) == 1
    assert apps[0].resume_draft == "Did a real thing"
    assert len(scheduler_env["sent_emails"]) == 1
    assert scheduler_env["sent_emails"][0]["match_score"] == 78


def test_retry_skips_job_already_fully_processed(monkeypatch, scheduler_env):
    session = scheduler_env["session"]
    job = _make_job(
        session,
        description="JOB_DONE",
        match_score=90,
        status=JobStatus.PENDING_APPROVAL,
    )
    session.add(Application(job_id=job.id, status=JobStatus.PENDING_APPROVAL))
    session.flush()

    scorer = FakeScorer({})
    rewriter = FakeRewriter()
    monkeypatch.setattr(scheduler_module, "MatchScorer", lambda: scorer)
    monkeypatch.setattr(scheduler_module, "ResumeRewriter", lambda: rewriter)

    result = scheduler_module.retry_pending_jobs()

    assert result == {"scored_now": 0, "tailored_now": 0}
    assert scorer.calls == []
    assert rewriter.calls == []
    assert scheduler_env["sent_emails"] == []


def test_retry_excludes_closed_jobs(monkeypatch, scheduler_env):
    session = scheduler_env["session"]
    _make_job(session, description="JOB_CLOSED", status=JobStatus.CLOSED)

    scorer = FakeScorer({})
    monkeypatch.setattr(scheduler_module, "MatchScorer", lambda: scorer)
    monkeypatch.setattr(scheduler_module, "ResumeRewriter", lambda: FakeRewriter())

    result = scheduler_module.retry_pending_jobs()

    assert result == {"scored_now": 0, "tailored_now": 0}
    assert scorer.calls == []
