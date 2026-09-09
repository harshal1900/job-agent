from __future__ import annotations

import json

import pytest

from llm.resume_rewriter import (
    HallucinationError,
    ResumeRewriter,
    build_fact_vocabulary,
    find_unsupported_terms,
)

PROFILE = {
    "personal": {"full_name": "Jane Doe"},
    "skills": ["Python", "SQL", "AWS"],
    "experience": [
        {
            "company": "Initech",
            "title": "Backend Engineer",
            "bullets": ["Built a Python service handling 10,000 requests per day"],
        }
    ],
}


class FakeLLMClient:
    def __init__(self, reply: str):
        self.reply = reply

    def chat(self, messages, temperature=0.2, max_tokens=1024):
        return self.reply


def test_build_fact_vocabulary_contains_known_facts():
    vocab = build_fact_vocabulary(PROFILE)
    assert "python" in vocab
    assert "initech" in vocab
    assert "10,000" in vocab


def test_find_unsupported_terms_flags_invented_company():
    vocab = build_fact_vocabulary(PROFILE)
    text = "Led backend work at Globex using Python and SQL."
    unsupported = find_unsupported_terms(text, vocab)
    assert "Globex" in unsupported
    assert "Python" not in unsupported


def test_rewrite_raises_on_hallucinated_output():
    reply = json.dumps(
        {
            "resume_bullets": ["Scaled Globex's infra to 1,000,000 users"],
            "cover_letter_paragraph": "I previously worked at Globex.",
        }
    )
    rewriter = ResumeRewriter(llm_client=FakeLLMClient(reply))

    with pytest.raises(HallucinationError):
        rewriter.rewrite(PROFILE, "Backend role", strict=True)


def test_rewrite_succeeds_when_grounded():
    reply = json.dumps(
        {
            "resume_bullets": [
                "Built a Python service at Initech handling 10,000 requests per day"
            ],
            "cover_letter_paragraph": "At Initech I worked as a Backend Engineer using Python.",
        }
    )
    rewriter = ResumeRewriter(llm_client=FakeLLMClient(reply))

    result = rewriter.rewrite(PROFILE, "Backend role", strict=True)
    assert result.unsupported_terms == []
    assert "Initech" in result.resume_bullets[0]
