from __future__ import annotations

import json

import pytest

from llm.resume_rewriter import (
    HallucinationError,
    ResumeRewriter,
    _REWRITE_MAX_TOKENS,
    _parse_rewrite_reply,
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
        self.last_max_tokens: int | None = None

    def chat(self, messages, temperature=0.2, max_tokens=1024):
        self.last_max_tokens = max_tokens
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


def test_rewrite_requests_a_higher_token_cap_to_avoid_truncation():
    reply = json.dumps({"resume_bullets": [], "cover_letter_paragraph": ""})
    client = FakeLLMClient(reply)
    rewriter = ResumeRewriter(llm_client=client)

    rewriter.rewrite(PROFILE, "Backend role", strict=True)

    # The old default (1024) was observed truncating real replies mid-JSON.
    assert client.last_max_tokens == _REWRITE_MAX_TOKENS
    assert client.last_max_tokens > 1024


def test_parse_rewrite_reply_raises_clear_error_on_truncated_json():
    # Cut off mid-string, exactly like the real truncation seen in production.
    truncated = (
        '{\n  "resume_bullets": [\n    "Built a Python service at Initech '
        'handling 10,000 requests per'
    )
    with pytest.raises(ValueError, match="looks truncated"):
        _parse_rewrite_reply(truncated)


def test_parse_rewrite_reply_raises_clear_error_on_malformed_json():
    # Has a { ... } span the regex will match, but it's not valid JSON
    # (trailing comma) — a different failure mode than truncation.
    malformed = '{"resume_bullets": ["a",], "cover_letter_paragraph": "b"}'
    with pytest.raises(ValueError, match="malformed JSON"):
        _parse_rewrite_reply(malformed)


def test_parse_rewrite_reply_raises_clear_error_when_no_json_present():
    with pytest.raises(ValueError, match="No JSON object found"):
        _parse_rewrite_reply("Sorry, I can't help with that.")


def test_rewrite_surfaces_clear_error_instead_of_crashing_on_truncated_reply():
    truncated = '{\n  "resume_bullets": [\n    "Built a Python service at Initech'
    rewriter = ResumeRewriter(llm_client=FakeLLMClient(truncated))

    with pytest.raises(ValueError, match="looks truncated"):
        rewriter.rewrite(PROFILE, "Backend role", strict=True)
