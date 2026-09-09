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
    if isinstance(obj, dict):
        return "".join(_flatten_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return "".join(_flatten_strings(v) for v in obj)
    return ""


def build_fact_vocabulary(profile: dict) -> set[str]:
    """Lowercased word tokens drawn from every string value in the profile."""
    text = _flatten_strings(profile)
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+\.#%,]*", text.lower())
    return set(words)


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


@dataclass
class RewriteResult:
    resume_bullets: list[str]
    cover_letter_paragraph: str
    unsupported_terms: list[str] = field(default_factory=list)


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
        vocabulary = build_fact_vocabulary(profile)

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
        )

        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {reply!r}")
        parsed = json.loads(match.group(0))

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
