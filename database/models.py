"""SQLAlchemy models: Job, Application, ApprovalToken.

Schema is written to be Postgres/Supabase-compatible even though SQLite is
the default dev backend — see db.py for the connection switch.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    NEW = "NEW"
    SCORED = "SCORED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUBMITTED = "SUBMITTED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class ATSType(str, enum.Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source_url", name="uq_jobs_source_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="")
    ats_type: Mapped[str] = mapped_column(Enum(ATSType), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(
        Enum(JobStatus), default=JobStatus.NEW, nullable=False
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    keyword_gaps: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)

    resume_draft: Mapped[str] = mapped_column(Text, default="")
    cover_letter_draft: Mapped[str] = mapped_column(Text, default="")
    prep_package: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded

    status: Mapped[str] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING_APPROVAL, nullable=False
    )
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["Job"] = relationship(back_populates="applications")
    tokens: Mapped[list["ApprovalToken"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class TokenAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalToken(Base):
    """Single-use, expiring token backing an email approval link.

    The token value itself is never the primary key lookup surface for
    guessing purposes — see api/security.py for signing/verification. This
    row exists so a token can be marked used exactly once (prevents replay
    from email link-scanners or a reused link).
    """

    __tablename__ = "approval_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), nullable=False)
    action: Mapped[str] = mapped_column(Enum(TokenAction), nullable=False)

    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    application: Mapped["Application"] = relationship(back_populates="tokens")

    @property
    def is_expired(self) -> bool:
        # SQLite (unlike Postgres) drops tzinfo on datetime round-trips, so
        # a value read back from the DB can come back naive even though it
        # was written as UTC-aware — reattach UTC before comparing.
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return _now() >= expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None
