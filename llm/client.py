"""LLM wrapper — OpenRouter (default) or Hugging Face Inference API.

Provider and model are entirely config-driven (config/settings.py /
.env: LLM_PROVIDER, OPENROUTER_MODEL, HF_MODEL) so swapping models never
requires touching call sites in llm/match_scorer.py or llm/resume_rewriter.py.
"""

from __future__ import annotations

import httpx

from config.settings import get_settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
HF_URL_TEMPLATE = "https://api-inference.huggingface.co/models/{model}"


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat-style prompt and return the model's text reply."""
        if self.settings.LLM_PROVIDER == "openrouter":
            return self._chat_openrouter(messages, temperature, max_tokens)
        if self.settings.LLM_PROVIDER == "huggingface":
            return self._chat_huggingface(messages, temperature, max_tokens)
        raise LLMError(f"Unknown LLM_PROVIDER: {self.settings.LLM_PROVIDER!r}")

    def _chat_openrouter(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        if not self.settings.OPENROUTER_API_KEY:
            raise LLMError("OPENROUTER_API_KEY is not set in .env")

        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.OPENROUTER_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        if response.status_code != 200:
            raise LLMError(
                f"OpenRouter request failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected OpenRouter response shape: {data}") from exc

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
            return data[0]["generated_text"]
        raise LLMError(f"Unexpected HF response shape: {data}")
