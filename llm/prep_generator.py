"""Generate an interview-prep package: STAR-format Q&A grounded in the
profile, plus a short list of topics/tutorial-style pointers for any
keyword gaps identified by match_scorer.

Like resume_rewriter, STAR answers are grounded in the profile — the prompt
instructs the model to build answers only from experience/projects already
listed, though this module does not run the hallucination guardrail itself
(the human approval step is expected to catch STAR-answer issues, since
these are prep notes for the candidate, not text submitted to an employer).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm.client import LLMClient

_PREP_PROMPT = """You are helping a candidate prepare for an interview for this job.

Candidate profile (JSON):
{profile_json}

Job description:
{job_description}

Keyword gaps (skills/requirements the profile doesn't clearly demonstrate):
{keyword_gaps}

Return ONLY a JSON object with this exact shape, no other text:
{{
  "star_questions": [
    {{
      "question": "<likely behavioral interview question for this role>",
      "situation": "<grounded in the candidate's actual experience/projects>",
      "task": "<...>",
      "action": "<...>",
      "result": "<...>"
    }}
  ],
  "study_topics": [
    {{"topic": "<gap topic>", "why": "<why it matters for this role>"}}
  ]
}}

Generate 3-5 star_questions and one study_topics entry per keyword gap.
"""


@dataclass
class PrepPackage:
    star_questions: list[dict]
    study_topics: list[dict]

    def to_json(self) -> str:
        return json.dumps(
            {"star_questions": self.star_questions, "study_topics": self.study_topics}
        )


class PrepGenerator:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def generate(
        self, profile: dict, job_description: str, keyword_gaps: list[str]
    ) -> PrepPackage:
        prompt = _PREP_PROMPT.format(
            profile_json=json.dumps(profile, indent=2),
            job_description=job_description,
            keyword_gaps=", ".join(keyword_gaps) or "(none identified)",
        )
        reply = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful interview-prep coach. "
                    "Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {reply!r}")
        parsed = json.loads(match.group(0))
        return PrepPackage(
            star_questions=list(parsed.get("star_questions", [])),
            study_topics=list(parsed.get("study_topics", [])),
        )
