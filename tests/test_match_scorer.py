from __future__ import annotations

import json

from llm.match_scorer import MatchScorer


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
