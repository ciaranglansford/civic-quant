"""OpenAI client wrapper for digest synthesis requests."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx


class DigestProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class DigestLlmResponse:
    used_openai: bool
    model_name: str
    openai_response_id: str | None
    latency_ms: int
    retries: int
    raw_text: str


class OpenAiDigestSynthesisClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        endpoint: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.endpoint = endpoint

    @staticmethod
    def _extract_output_text(body: dict) -> str:
        output = body.get("output", [])
        if not isinstance(output, list):
            raise DigestProviderError("invalid output payload type")

        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") in {"output_text", "text"}:
                    text = chunk.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())

        if texts:
            return "\n".join(texts).strip()

        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        if isinstance(output_text, list):
            joined = "\n".join(str(x).strip() for x in output_text if str(x).strip()).strip()
            if joined:
                return joined

        raise DigestProviderError("empty model response")

    def synthesize(self, prompt_text: str) -> DigestLlmResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "text": {"format": {"type": "json_object"}},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": "Return strict JSON only. Do not wrap in markdown."}
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt_text}],
                },
            ],
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                raw_text = self._extract_output_text(body)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                return DigestLlmResponse(
                    used_openai=True,
                    model_name=str(body.get("model") or self.model),
                    openai_response_id=body.get("id"),
                    latency_ms=latency_ms,
                    retries=attempt,
                    raw_text=raw_text,
                )
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, DigestProviderError) as exc:
                last_error = exc

        raise DigestProviderError(f"openai request failed after retries: {type(last_error).__name__}")
