"""LLM wrapper — Gemini (default), OpenRouter, or Hugging Face Inference API.

Provider and model are entirely config-driven (config/settings.py /
.env: LLM_PROVIDER, GEMINI_MODEL, OPENROUTER_MODEL, HF_MODEL) so swapping
models never requires touching call sites in llm/match_scorer.py or
llm/resume_rewriter.py.

Gemini is called via its native generateContent endpoint, not the
OpenAI-compatible one. As of Google's Sept 2026 migration off "Standard"
(AIza...) keys to "Auth" (AQ....) keys, Auth keys are broken against the
OpenAI-compatible endpoint (fails with "Multiple authentication credentials
received" / 401) — confirmed on Google's own AI developer forum, still
unresolved as of this writing. The native endpoint with an `x-goog-api-key`
header works correctly with both key formats, so that's what we use here.
OpenRouter keeps using the shared OpenAI-compatible helper below since it
only ever issues standard bearer-token keys.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from config.settings import get_settings

logger = logging.getLogger(__name__)

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
HF_URL_TEMPLATE = "https://api-inference.huggingface.co/models/{model}"

# Gemini's free tier caps flash-lite models at 15 requests/minute per
# project — a batch job (retry-pending, a scan cycle) creates a fresh
# LLMClient per posting and fires requests back-to-back, which blows
# through that in seconds and then fails nearly every subsequent call with
# a 429 instead of actually using the per-minute budget. This is a
# process-wide (not per-instance) throttle so it holds regardless of how
# many LLMClient objects get created. 4.5s spacing keeps us under 15 RPM
# with margin; retrying on 429 wouldn't help further since the daily quota
# is the next ceiling up and retrying won't make that reset any sooner.
_GEMINI_MIN_INTERVAL_SECONDS = 4.5
_gemini_rate_lock = threading.Lock()
_gemini_last_call_at = 0.0


class LLMError(RuntimeError):
    pass


class EmptyLLMResponseError(LLMError):
    """Raised when the provider returns a null/empty message body — seen
    intermittently from free-tier OpenRouter models. chat() retries on this
    specific error before giving up; it is never raised for other failures
    (bad auth, rate limits, malformed response shape), which fail fast
    instead since retrying wouldn't help."""


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> str:
        """Send a chat-style prompt and return the model's text reply.

        Retries up to `max_retries` times if the provider returns a
        null/empty message body, since that's been observed to be
        transient rather than a real failure. Any other error (bad auth,
        rate limit, malformed response) is raised immediately without
        retrying.
        """
        last_error: EmptyLLMResponseError | None = None
        for attempt in range(1, max_retries + 2):
            try:
                return self._dispatch(messages, temperature, max_tokens)
            except EmptyLLMResponseError as exc:
                last_error = exc
                logger.warning(
                    "LLM returned empty/null content on attempt %d/%d — %s",
                    attempt,
                    max_retries + 1,
                    "retrying" if attempt <= max_retries else "giving up",
                )
                if attempt <= max_retries:
                    time.sleep(retry_delay_seconds)

        assert last_error is not None
        raise last_error

    def _dispatch(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        if self.settings.LLM_PROVIDER == "gemini":
            return self._chat_gemini(messages, temperature, max_tokens)
        if self.settings.LLM_PROVIDER == "openrouter":
            return self._chat_openrouter(messages, temperature, max_tokens)
        if self.settings.LLM_PROVIDER == "huggingface":
            return self._chat_huggingface(messages, temperature, max_tokens)
        raise LLMError(f"Unknown LLM_PROVIDER: {self.settings.LLM_PROVIDER!r}")

    def _chat_openai_compatible(
        self,
        *,
        provider_name: str,
        url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Shared request/response handling for any OpenAI-compatible chat
        completions endpoint (Gemini's compat layer and OpenRouter both use
        this exact shape)."""
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        if response.status_code != 200:
            raise LLMError(
                f"{provider_name} request failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected {provider_name} response shape: {data}") from exc

        if not content:
            raise EmptyLLMResponseError(
                f"{provider_name} returned null/empty message content: {data}"
            )
        return content

    @staticmethod
    def _throttle_gemini() -> None:
        """Block until enough time has passed since the last Gemini call to
        stay under the free tier's per-minute cap. See module-level comment
        on _GEMINI_MIN_INTERVAL_SECONDS."""
        global _gemini_last_call_at
        with _gemini_rate_lock:
            now = time.monotonic()
            wait = _GEMINI_MIN_INTERVAL_SECONDS - (now - _gemini_last_call_at)
            if wait > 0:
                time.sleep(wait)
            _gemini_last_call_at = time.monotonic()

    def _chat_gemini(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        if not self.settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not set in .env")

        self._throttle_gemini()

        # Gemini's native API has no "system" role — system messages go in a
        # separate systemInstruction block, and everything else is "user" or
        # "model" (not "assistant").
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
            if m["role"] != "system"
        ]

        generation_config: dict = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        # Non-lite Gemini 3.x models spend part of maxOutputTokens on
        # internal "thinking" before the visible reply, so a hard-enough
        # prompt can burn the whole budget on reasoning and truncate the
        # actual answer (reproduced locally: max_tokens=50 -> ~100 thinking
        # tokens -> truncated garbage). We don't need chain-of-thought for
        # scoring/tailoring, so disable it — but only on models that support
        # the field at all: "-lite" models reject thinkingConfig outright
        # (400 INVALID_ARGUMENT) since they never think in the first place.
        if "lite" not in self.settings.GEMINI_MODEL:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

        body: dict = {"contents": contents, "generationConfig": generation_config}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = GEMINI_URL_TEMPLATE.format(model=self.settings.GEMINI_MODEL)
        response = httpx.post(
            url,
            headers={
                "x-goog-api-key": self.settings.GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60.0,
        )
        if response.status_code != 200:
            raise LLMError(f"Gemini request failed ({response.status_code}): {response.text}")

        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            content = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc

        if not content:
            raise EmptyLLMResponseError(f"Gemini returned null/empty message content: {data}")
        return content

    def _chat_openrouter(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        if not self.settings.OPENROUTER_API_KEY:
            raise LLMError("OPENROUTER_API_KEY is not set in .env")

        return self._chat_openai_compatible(
            provider_name="OpenRouter",
            url=OPENROUTER_URL,
            api_key=self.settings.OPENROUTER_API_KEY,
            model=self.settings.OPENROUTER_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _chat_huggingface(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        if not self.settings.HF_API_TOKEN or not self.settings.HF_MODEL:
            raise LLMError("HF_API_TOKEN / HF_MODEL are not set in .env")

        prompt = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        response = httpx.post(
            HF_URL_TEMPLATE.format(model=self.settings.HF_MODEL),
            headers={"Authorization": f"Bearer {self.settings.HF_API_TOKEN}"},
            json={
                "inputs": prompt,
                "parameters": {
                    "temperature": temperature,
                    "max_new_tokens": max_tokens,
                    "return_full_text": False,
                },
            },
            timeout=60.0,
        )
        if response.status_code != 200:
            raise LLMError(
                f"HF Inference request failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        if isinstance(data, list) and data and "generated_text" in data[0]:
            generated_text = data[0]["generated_text"]
            if not generated_text:
                raise EmptyLLMResponseError(
                    f"HF Inference returned null/empty generated_text: {data}"
                )
            return generated_text
        raise LLMError(f"Unexpected HF response shape: {data}")
