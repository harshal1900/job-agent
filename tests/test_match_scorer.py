from __future__ import annotations

import json

import pytest

from llm.match_scorer import MatchScorer, _extract_json


class FakeLLMClient:
    def __init__(self, reply: str):
        self.reply = reply

    def chat(self, messages, temperature=0.2, max_tokens=1024):
        return self.reply


def test_score_parses_llm_json_reply():
    reply = json.dumps(
        {
            "match_score": 82,
            "keyword_gaps": ["Kubernetes", "GraphQL"],
            "rationale": "Strong backend overlap, missing some infra tooling.",
        }
    )
    scorer = MatchScorer(llm_client=FakeLLMClient(reply))

    result = scorer.score({"skills": ["Python"]}, "We need a backend engineer.")

    assert result.match_score == 82
    assert result.keyword_gaps == ["Kubernetes", "GraphQL"]
    assert "backend" in result.rationale.lower()


def test_score_handles_reply_with_surrounding_text():
    reply = f"Here you go:\n{json.dumps({'match_score': 50, 'keyword_gaps': [], 'rationale': 'ok'})}\nThanks."
    scorer = MatchScorer(llm_client=FakeLLMClient(reply))

    result = scorer.score({}, "JD text")

    assert result.match_score == 50


def test_extract_json_raises_clear_error_on_none_instead_of_typeerror():
    with pytest.raises(ValueError, match="empty/non-string content"):
        _extract_json(None)


def test_extract_json_raises_clear_error_on_empty_string():
    with pytest.raises(ValueError, match="empty/non-string content"):
        _extract_json("")


def test_score_surfaces_clear_error_when_llm_client_returns_none():
    # Regression test: previously a None reply crashed deep inside re.search
    # with a bare "TypeError: expected string or bytes-like object, got
    # 'NoneType'" instead of a clear, actionable error.
    scorer = MatchScorer(llm_client=FakeLLMClient(None))

    with pytest.raises(ValueError, match="empty/non-string content"):
        scorer.score({}, "JD text")
