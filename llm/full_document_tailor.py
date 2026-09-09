"""Full-document tailoring: a complete resume (all roles, all bullets, all
sections) and a full business-letter-format cover letter, both grounded
against the same anti-hallucination guardrail as the short-form rewrite in
resume_rewriter.py.

This is deliberately a separate module from resume_rewriter.py rather than
an extension of it: the short-form rewrite is designed to *select* a handful
of the most relevant bullets, while this is designed to *keep every bullet*
(reworded/reordered for relevance) so the output is a real, complete resume
rather than a highlights snippet. Reuses resume_rewriter's guardrail
primitives (build_fact_vocabulary, find_unsupported_terms, HallucinationError)
rather than duplicating them, so there is exactly one definition of "what
counts as a grounded fact" across both code paths.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from llm.client import LLMClient
from llm.resume_rewriter import (
    HallucinationError,
    _parse_rewrite_reply,
    _tokenize,
    build_fact_vocabulary,
    find_unsupported_terms,
)

logger = logging.getLogger(__name__)

# A full resume (every bullet across every role, reworded) plus a full
# business letter runs well past the short-form rewrite's budget -- this
# is sized for ~20-30 achievement bullets plus a 4-paragraph letter.
_FULL_DOCUMENT_MAX_TOKENS = 4096

_FULL_RESUME_PROMPT = """You are tailoring a candidate's COMPLETE resume for a specific job. \
Unlike a highlights snippet, this must preserve every single role and every \
single achievement bullet from the candidate's real history below -- you may \
ONLY reorder bullets within a role (most relevant to this job first) and \
reword them for clarity/emphasis, using ONLY facts already stated in that \
bullet or elsewhere in the profile. Do NOT invent, drop, merge, or add \
bullets, employers, titles, dates, tools, or metrics. Do NOT invent facts not \
grounded in the profile.

Candidate profile (JSON):
{profile_json}

Job description:
{job_description}

The profile's "professional_experience" list has {num_roles} roles, indexed \
0 to {max_index}. For EACH index, return EXACTLY the same number of \
achievement bullets as that role has in the profile -- reordered and \
reworded only, never added or removed.

Return ONLY a JSON object with this exact shape, no other text:
{{
  "tailored_summary": "<2-4 sentence professional summary, grounded in the profile, tailored to this job>",
  "experience": [
    {{"index": 0, "achievements": ["<reworded bullet 1>", "<reworded bullet 2>", ...]}},
    ...
  ]
}}
"""

_COVER_LETTER_PROMPT = """You are writing a COMPLETE, professional cover letter for the candidate \
below applying to a specific job. Use ONLY facts already stated in the \
candidate profile JSON. Do NOT invent employers, titles, dates, tools, \
metrics, or achievements not present in the profile. You may reference the \
target company name and role title, and general facts stated in the job \
description itself -- that is not inventing a candidate fact, since it's \
already grounded in text you were given.

Candidate profile (JSON):
{profile_json}

Company: {company}
Role: {role_title}
Job description:
{job_description}

Write a complete business letter with this structure:
1. An opening paragraph that names the company and role and states genuine interest.
2. Two to three body paragraphs connecting specific, real experience from the \
profile to specific requirements stated in the job description.
3. A closing paragraph reiterating interest and inviting next steps.

Return ONLY a JSON object with this exact shape, no other text:
{{
  "opening_paragraph": "...",
  "body_paragraphs": ["...", "..."],
  "closing_paragraph": "..."
}}
"""


class DocumentStructureError(RuntimeError):
    """Raised when the LLM's reply doesn't preserve the profile's actual
    structure (wrong achievement count for a role, wrong role count,
    unrecognized index) -- a distinct failure mode from HallucinationError,
    since the content could be perfectly grounded and still violate "keep
    the full resume structure intact"."""


@dataclass
class TailoredExperienceEntry:
    title: str
    company: str
    location: str | None
    start_date: str | None
    end_date: str | None
    achievements: list[str]


@dataclass
class FullResumeResult:
    tailored_summary: str
    experience: list[TailoredExperienceEntry]
    unsupported_terms: list[str] = field(default_factory=list)


@dataclass
class FullCoverLetterResult:
    opening_paragraph: str
    body_paragraphs: list[str]
    closing_paragraph: str
    unsupported_terms: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(
            [self.opening_paragraph, *self.body_paragraphs, self.closing_paragraph]
        )


class FullDocumentTailor:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def tailor_resume(
        self, profile: dict, job_description: str, strict: bool = True
    ) -> FullResumeResult:
        roles = profile.get("professional_experience", [])
        if not roles:
            raise DocumentStructureError(
                "profile has no professional_experience entries to tailor"
            )

        prompt = _FULL_RESUME_PROMPT.format(
            profile_json=json.dumps(profile, indent=2),
            job_description=job_description,
            num_roles=len(roles),
            max_index=len(roles) - 1,
        )
        reply = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, honest resume-tailoring assistant. "
                    "You never invent, add, or drop facts. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=_FULL_DOCUMENT_MAX_TOKENS,
        )
        parsed = _parse_rewrite_reply(reply)

        tailored_summary = str(parsed.get("tailored_summary", "")).strip()
        by_index = {
            entry.get("index"): entry.get("achievements", [])
            for entry in parsed.get("experience", [])
            if isinstance(entry, dict)
        }

        experience: list[TailoredExperienceEntry] = []
        for i, role in enumerate(roles):
            original_achievements = role.get("achievements", [])
            reworded = by_index.get(i)

            if not isinstance(reworded, list) or len(reworded) != len(original_achievements):
                # Structural violation -- the model dropped/added a bullet
                # or skipped this role entirely. Falling back to the
                # original, untailored bullets for just this one role is
                # safer than either crashing the whole document or
                # silently accepting a resume with missing achievements.
                logger.warning(
                    "Full resume tailoring for role %d (%s at %s) returned "
                    "%s achievements, expected %d -- using original bullets "
                    "for this role instead of the (structurally invalid) rewrite.",
                    i,
                    role.get("title"),
                    role.get("company"),
                    "no entry" if reworded is None else len(reworded),
                    len(original_achievements),
                )
                reworded = list(original_achievements)

            experience.append(
                TailoredExperienceEntry(
                    title=role.get("title", ""),
                    company=role.get("company", ""),
                    location=role.get("location"),
                    start_date=role.get("start_date"),
                    end_date=role.get("end_date"),
                    achievements=[str(a) for a in reworded],
                )
            )

        vocabulary = build_fact_vocabulary(profile) | _tokenize(job_description)
        full_text = tailored_summary + "\n" + "\n".join(
            a for entry in experience for a in entry.achievements
        )
        unsupported = find_unsupported_terms(full_text, vocabulary)
        if unsupported and strict:
            raise HallucinationError(
                "Full resume tailoring contains terms not traceable to "
                f"master_profile.json or the job description: {unsupported}"
            )

        return FullResumeResult(
            tailored_summary=tailored_summary,
            experience=experience,
            unsupported_terms=unsupported,
        )

    def tailor_cover_letter(
        self,
        profile: dict,
        company: str,
        role_title: str,
        job_description: str,
        strict: bool = True,
    ) -> FullCoverLetterResult:
        prompt = _COVER_LETTER_PROMPT.format(
            profile_json=json.dumps(profile, indent=2),
            company=company,
            role_title=role_title,
            job_description=job_description,
        )
        reply = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, honest cover-letter-writing assistant. "
                    "You never invent facts. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=_FULL_DOCUMENT_MAX_TOKENS,
        )
        parsed = _parse_rewrite_reply(reply)

        opening = str(parsed.get("opening_paragraph", "")).strip()
        body = [str(p).strip() for p in parsed.get("body_paragraphs", []) if str(p).strip()]
        closing = str(parsed.get("closing_paragraph", "")).strip()

        if not opening or not body or not closing:
            raise DocumentStructureError(
                f"Cover letter reply is missing a required section (opening={bool(opening)}, "
                f"body_paragraphs={len(body)}, closing={bool(closing)})"
            )

        # The prompt explicitly asks the model to name the company and role
        # -- those terms must be grounded the same way job_description's
        # terms are, or every cover letter would flag its own greeting.
        vocabulary = (
            build_fact_vocabulary(profile)
            | _tokenize(job_description)
            | _tokenize(company)
            | _tokenize(role_title)
        )
        full_text = "\n\n".join([opening, *body, closing])
        unsupported = find_unsupported_terms(full_text, vocabulary)
        if unsupported and strict:
            raise HallucinationError(
                "Cover letter contains terms not traceable to master_profile.json "
                f"or the job description: {unsupported}"
            )

        return FullCoverLetterResult(
            opening_paragraph=opening,
            body_paragraphs=body,
            closing_paragraph=closing,
            unsupported_terms=unsupported,
        )
