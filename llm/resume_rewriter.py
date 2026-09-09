"""Anti-hallucination-guarded resume/cover-letter tailoring.

The LLM is instructed to only reorder/reword facts already present in
master_profile.json. Because instructions alone can't be trusted, every
rewrite is passed through find_unsupported_terms() afterward as a mechanical
guardrail: any number or proper-noun-like token in the output that doesn't
trace back to the profile JSON is flagged. This is a heuristic, not full NLP
fact-checking — it catches invented companies, tools, metrics, and dates,
which are the highest-risk hallucinations. It does not replace human review;
the email approval step is still the final backstop before anything is sent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from llm.client import LLMClient

_REWRITE_PROMPT = """You are tailoring a candidate's resume bullets and a short cover letter \
paragraph for a specific job. You may ONLY reorder, reword, condense, or \
re-emphasize facts that already appear in the candidate profile JSON below. \
Do NOT invent employers, titles, dates, tools, metrics, or achievements that \
are not present in the profile. If the job wants something the profile \
doesn't support, simply omit it rather than fabricating it.

Candidate profile (JSON):
{profile_json}

Job description:
{job_description}

Return ONLY a JSON object with this exact shape, no other text:
{{
  "resume_bullets": ["<tailored bullet grounded in the profile>", ...],
  "cover_letter_paragraph": "<one paragraph, grounded in the profile only>"
}}
"""

# Common words that are safe to use in any rewrite regardless of whether they
# appear verbatim in the profile (connectors, generic resume verbs, etc.) —
# these are never themselves "facts".
_SAFE_WORDS = {
    "a", "an", "and", "the", "of", "in", "on", "for", "to", "with", "by",
    "as", "at", "from", "or", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "i", "my", "our",
    "led", "built", "drove", "managed", "developed", "designed",
    "implemented", "delivered", "improved", "increased", "reduced",
    "created", "launched", "owned", "collaborated", "partnered",
    "spearheaded", "streamlined", "optimized", "years", "year", "team",
    "teams", "cross-functional", "role", "responsible", "including",
    "using", "across", "within", "through", "while", "also", "new",
}

_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z0-9\+\#\.]*\b")
_NUMBER_RE = re.compile(r"\b\d[\d,\.]*%?\b")


def _flatten_strings(obj) -> str:
    if isinstance(obj, str):
        return obj + " "
    # bool is a subclass of int -- exclude it so True/False don't get
    # stringified into meaningless vocabulary noise.
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return str(obj) + " "
    if isinstance(obj, dict):
        return "".join(_flatten_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return "".join(_flatten_strings(v) for v in obj)
    return ""


_TRAILING_PUNCT = ".,+%"


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+\.#%,]*", text.lower())
    vocab = set(words)

    # This regex is deliberately loose (keeps "+"/"."/"%"/"," attached) so
    # it can grab compound tokens like "14+", "u.s.", "40-60%" whole. But
    # find_unsupported_terms() extracts candidates from the *generated*
    # text with a stricter \b-bounded regex that can't end a match on
    # trailing punctuation, and can't span a "-" the way this one does --
    # so "14+" here vs. "14" there, or "40-60%" here vs. "40"/"60" there,
    # would otherwise never match even though they're the same grounded
    # fact. Derive and index the forms the other regex would actually
    # produce: trailing punctuation stripped, and each hyphen-separated
    # part on its own (for ranges like "40-60%" and compounds like
    # "co-designing").
    derived: set[str] = set()
    for word in vocab:
        stripped = word.rstrip(_TRAILING_PUNCT)
        if stripped:
            derived.add(stripped)
        if "-" in word:
            for part in word.split("-"):
                part = part.rstrip(_TRAILING_PUNCT)
                if part:
                    derived.add(part)
    vocab |= derived
    return vocab


def build_fact_vocabulary(profile: dict) -> set[str]:
    """Lowercased word tokens drawn from every string/number value in the
    profile, including trailing-'+' variants of numbers ("14+" -> "14")."""
    return _tokenize(_flatten_strings(profile))


def find_unsupported_terms(text: str, vocabulary: set[str]) -> list[str]:
    """Flag numbers/proper-noun-like tokens in `text` absent from `vocabulary`.

    Heuristic guardrail, not exhaustive fact-checking — see module docstring.
    """
    candidates = _PROPER_NOUN_RE.findall(text) + _NUMBER_RE.findall(text)

    unsupported: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        key = term.lower()
        if key in seen or key in _SAFE_WORDS:
            continue
        if key not in vocabulary:
            unsupported.append(term)
            seen.add(key)
    return unsupported


class HallucinationError(RuntimeError):
    """Raised when a rewrite contains terms not traceable to the profile."""


# Resume bullets + a cover letter paragraph for a detailed, senior-level
# profile can comfortably exceed LLMClient.chat()'s default 1024-token cap,
# which silently truncates the reply mid-JSON rather than erroring — this
# was observed in practice cutting a reply off mid-string with no closing
# brace. 2048 gives real headroom without being wastefully large.
_REWRITE_MAX_TOKENS = 2048


@dataclass
class RewriteResult:
    resume_bullets: list[str]
    cover_letter_paragraph: str
    unsupported_terms: list[str] = field(default_factory=list)


def _parse_rewrite_reply(reply: str) -> dict:
    """Parse the rewrite JSON reply, raising a clear, specific ValueError
    instead of a bare crash (or, previously, an unguarded json.JSONDecodeError)
    when the reply is truncated or otherwise malformed. A raised error here
    leaves the Job at SCORED with no Application row, which
    api/scheduler.py's retry_pending_jobs() will pick back up on the next
    retry pass — so failing loudly and specifically (rather than silently
    producing nothing) is what makes that retry actually effective.
    """
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        preview = reply[:200]
        if reply.strip().startswith("{"):
            raise ValueError(
                "Rewrite response looks truncated (starts with '{' but has no "
                f"closing '}}' anywhere in {len(reply)} chars) — preview: {preview!r}"
            )
        raise ValueError(f"No JSON object found in rewrite response — preview: {preview!r}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        preview = match.group(0)[:200]
        raise ValueError(
            f"Rewrite response contains malformed JSON ({exc}) — preview: {preview!r}"
        ) from exc


class ResumeRewriter:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def rewrite(
        self, profile: dict, job_description: str, strict: bool = True
    ) -> RewriteResult:
        """Tailor resume bullets + a cover letter paragraph for one job.

        If strict=True (default), raises HallucinationError when the
        guardrail flags unsupported terms instead of returning them —
        callers that want to inspect/log flagged terms without raising
        should pass strict=False.
        """
        # A tailored cover letter legitimately echoes back terms from the
        # job posting itself (the role title, the company name, "U.S.",
        # etc.) — that's not the model inventing a candidate fact, since
        # it's already grounded in text the model was actually given. Only
        # flag terms present in NEITHER the profile NOR the job posting.
        vocabulary = build_fact_vocabulary(profile) | _tokenize(job_description)

        prompt = _REWRITE_PROMPT.format(
            profile_json=json.dumps(profile, indent=2),
            job_description=job_description,
        )
        reply = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, honest resume-tailoring assistant. "
                    "You never invent facts. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=_REWRITE_MAX_TOKENS,
        )

        parsed = _parse_rewrite_reply(reply)

        bullets = list(parsed.get("resume_bullets", []))
        cover_paragraph = str(parsed.get("cover_letter_paragraph", ""))
        full_text = "\n".join(bullets) + "\n" + cover_paragraph

        unsupported = find_unsupported_terms(full_text, vocabulary)
        if unsupported and strict:
            raise HallucinationError(
                "Rewrite contains terms not traceable to master_profile.json: "
                f"{unsupported}"
            )

        return RewriteResult(
            resume_bullets=bullets,
            cover_letter_paragraph=cover_paragraph,
            unsupported_terms=unsupported,
        )
