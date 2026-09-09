"""Score a job description against master_profile.json and list keyword gaps."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm.client import LLMClient

_SCORING_PROMPT = """You are scoring how well a candidate's profile matches a job description.

Candidate profile (JSON):
{profile_json}

Job description:
{job_description}

Return ONLY a JSON object with this exact shape, no other text:
{{
  "match_score": <integer 0-100>,
  "keyword_gaps": ["<skill/requirement mentioned in the JD but not evidenced in the profile>", ...],
  "rationale": "<one or two sentence explanation>"
}}
"""


@dataclass
class MatchResult:
    match_score: int
    keyword_gaps: list[str]
    rationale: str


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text!r}")
    return json.loads(match.group(0))


class MatchScorer:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def score(self, profile: dict, job_description: str) -> MatchResult:
        prompt = _SCORING_PROMPT.format(
            profile_json=json.dumps(profile, indent=2),
            job_description=job_description,
        )
        reply = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise, concise job-matching assistant. "
                    "Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        parsed = _extract_json(reply)
        return MatchResult(
            match_score=int(parsed.get("match_score", 0)),
            keyword_gaps=list(parsed.get("keyword_gaps", [])),
            rationale=str(parsed.get("rationale", "")),
        )
