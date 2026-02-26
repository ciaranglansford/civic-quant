from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmResponse:
    model_name: str
    raw_text: str


class OpenAiExtractionClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.endpoint = endpoint

    def extract(self, prompt_text: str) -> LlmResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return only strict JSON matching the requested schema."},
                {"role": "user", "content": prompt_text},
            ],
        }

        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    r = client.post(self.endpoint, headers=headers, json=payload)
                r.raise_for_status()
                body = r.json()
                raw_text = _extract_response_text(body).strip()
                if not raw_text:
                    raise ProviderError("empty model response")
                return LlmResponse(model_name=self.model, raw_text=raw_text)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ProviderError) as e:
                last_error = e
        raise ProviderError(f"openai request failed after retries: {type(last_error).__name__}")


def _extract_response_text(body: dict[str, Any]) -> str:
    """
    Extract text payload from OpenAI chat-completions style responses.

    Supports both legacy string `message.content` and structured content blocks.
    """
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderError("missing message")

    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        combined = "".join(text_parts)
        if combined:
            return combined

    raise ProviderError("missing content text")
