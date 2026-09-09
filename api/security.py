"""Signed, single-use, expiring tokens for approval links.

Design (see docs/PRD.md risk #2 — a bare job id in a GET query string lets
anyone with the link approve/reject on your behalf):

1. Signing: itsdangerous.URLSafeTimedSerializer signs {application_id,
   action, nonce} with APPROVAL_TOKEN_SECRET. This proves the token wasn't
   forged and lets us cheaply check its age.
2. Single-use: a SHA-256 hash of the signed token is stored in the
   approval_tokens table (see database/models.py) with used_at=NULL.
   Verifying a token also atomically marks it used — a second attempt with
   the same link fails even if the signature and expiry are still valid.
   This is what actually stops email link-scanners and reused links, since
   itsdangerous alone only proves authenticity/age, not one-time use.
3. Expiry: enforced twice — itsdangerous max_age AND the DB row's
   expires_at — so a token can't outlive either check.

Callers MUST treat the approval action itself (routes_approval.py) as a POST
from a landing page, never a bare GET, so that email security scanners that
pre-fetch links can't silently consume the token.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.models import ApprovalToken, TokenAction

_SALT = "job-agent-approval-token"


class TokenError(RuntimeError):
    """Raised for any invalid, expired, tampered, or already-used token."""


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.APPROVAL_TOKEN_SECRET:
        raise RuntimeError(
            "APPROVAL_TOKEN_SECRET is not set in .env — generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"`"
        )
    return URLSafeTimedSerializer(settings.APPROVAL_TOKEN_SECRET, salt=_SALT)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass
class IssuedToken:
    raw_token: str
    expires_at: datetime


def issue_token(
    session: Session, application_id: str, action: TokenAction
) -> IssuedToken:
    """Create and persist a new signed, single-use approval token."""
    settings = get_settings()
    nonce = secrets.token_urlsafe(16)

    raw_token = _serializer().dumps(
        {"application_id": application_id, "action": action.value, "nonce": nonce}
    )
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.APPROVAL_TOKEN_TTL_SECONDS
    )

    row = ApprovalToken(
        application_id=application_id,
        action=action,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()

    return IssuedToken(raw_token=raw_token, expires_at=expires_at)


def peek_token(raw_token: str) -> dict:
    """Decode a token's payload (signature + expiry checked) WITHOUT
    consuming it — safe to call repeatedly, e.g. to render the confirmation
    landing page on GET before the user has clicked the real POST button.
    Never treat a successful peek as authorization to act; only
    verify_and_consume_token does that.
    """
    settings = get_settings()
    try:
        return _serializer().loads(
            raw_token, max_age=settings.APPROVAL_TOKEN_TTL_SECONDS
        )
    except SignatureExpired as exc:
        raise TokenError("Approval link has expired.") from exc
    except BadSignature as exc:
        raise TokenError("Approval link is invalid or was tampered with.") from exc


def verify_and_consume_token(session: Session, raw_token: str) -> ApprovalToken:
    """Validate signature, expiry, and single-use status; mark the token used.

    Raises TokenError on any failure. On success, the returned row's
    used_at has already been set and flushed — callers should not call this
    twice for the same click.
    """
    settings = get_settings()
    try:
        payload = _serializer().loads(
            raw_token, max_age=settings.APPROVAL_TOKEN_TTL_SECONDS
        )
    except SignatureExpired as exc:
        raise TokenError("Approval link has expired.") from exc
    except BadSignature as exc:
        raise TokenError("Approval link is invalid or was tampered with.") from exc

    token_hash = _hash_token(raw_token)
    row = (
        session.query(ApprovalToken)
        .filter(ApprovalToken.token_hash == token_hash)
        .one_or_none()
    )
    if row is None:
        raise TokenError("Approval link is unrecognized.")
    if row.application_id != payload.get("application_id"):
        raise TokenError("Approval link payload mismatch.")
    if row.is_used:
        raise TokenError("Approval link has already been used.")
    if row.is_expired:
        raise TokenError("Approval link has expired.")

    row.used_at = datetime.now(timezone.utc)
    session.add(row)
    session.flush()

    return row
