from __future__ import annotations

import pytest

from llm.client import EmptyLLMResponseError, LLMClient
from config.settings import get_settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _null_content_response():
    return _FakeResponse(
        200, {"choices": [{"message": {"content": None}}]}
    )


def _valid_response(content: str):
    return _FakeResponse(200, {"choices": [{"message": {"content": content}}]})


@pytest.fixture
def openrouter_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    get_settings.cache_clear()
    yield LLMClient()
    get_settings.cache_clear()


def test_chat_retries_then_succeeds_on_null_content(monkeypatch, openrouter_client):
    responses = [_null_content_response(), _null_content_response(), _valid_response("real reply")]
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        response = responses[calls["count"]]
        calls["count"] += 1
        return response

    monkeypatch.setattr("llm.client.httpx.post", fake_post)

    result = openrouter_client.chat(
        messages=[{"role": "user", "content": "hi"}],
        max_retries=2,
        retry_delay_seconds=0,
    )

    assert result == "real reply"
    assert calls["count"] == 3


def test_chat_raises_clear_error_after_exhausting_retries(monkeypatch, openrouter_client):
    monkeypatch.setattr("llm.client.httpx.post", lambda *a, **k: _null_content_response())

    with pytest.raises(EmptyLLMResponseError):
        openrouter_client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_retries=1,
            retry_delay_seconds=0,
        )
