from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from ..config import Settings
from ..schemas import (
    QueryNewsResponse,
    QueryNewsResultItem,
    QuerySummaryPayload,
    QuerySummaryPoint,
    QuerySummaryResponse,
    QueryWindow,
)


_WS_RE = re.compile(r"\s+")
_UNCERTAINTY_MARKERS = (
    "reportedly",
    "according to",
    "unconfirmed",
    "unclear",
    "disputed",
    "claims",
    "alleged",
    "may",
    "could",
    "might",
)


class QuerySummaryProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuerySummaryLlmResponse:
    model_name: str
    openai_response_id: str | None
    latency_ms: int
    retries: int
    raw_text: str


class OpenAiQuerySummaryClient:
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
            raise QuerySummaryProviderError("invalid output payload type")

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
            joined = "\n".join(str(value).strip() for value in output_text if str(value).strip()).strip()
            if joined:
                return joined
        raise QuerySummaryProviderError("empty model response")

    def summarize(self, prompt_text: str) -> QuerySummaryLlmResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "text": {"format": {"type": "json_object"}},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You summarize reported developments. Preserve attribution and uncertainty. "
                                "Return strict JSON only."
                            ),
                        }
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": prompt_text}]},
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
                return QuerySummaryLlmResponse(
                    model_name=str(body.get("model") or self.model),
                    openai_response_id=body.get("id"),
                    latency_ms=latency_ms,
                    retries=attempt,
                    raw_text=raw_text,
                )
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, QuerySummaryProviderError) as exc:
                last_error = exc
        raise QuerySummaryProviderError(f"openai request failed after retries: {type(last_error).__name__}")


class _StrictPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_refs: list[str]


class _StrictSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_developments: list[_StrictPoint]
    uncertainties: list[_StrictPoint]
    why_it_matters: list[_StrictPoint]


def _clean_text(value: str | None) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def _has_uncertainty(text: str) -> bool:
    lowered = _clean_text(text).lower()
    return any(marker in lowered for marker in _UNCERTAINTY_MARKERS)


def _attributed_claim(claim: str) -> str:
    cleaned = _clean_text(claim)
    if not cleaned:
        return "Reported developments were noted."
    if _has_uncertainty(cleaned):
        return cleaned
    return f"Reportedly, {cleaned[0].lower() + cleaned[1:] if len(cleaned) > 1 else cleaned.lower()}"


def _refs_for_item(item: QueryNewsResultItem) -> list[str]:
    refs: list[str] = [f"evt_{item.event_id}"]
    refs.extend(item.evidence_refs[:1])
    return refs


def _deterministic_summary(*, topic: str, window: QueryWindow, results: list[QueryNewsResultItem]) -> QuerySummaryPayload:
    if not results:
        return QuerySummaryPayload(
            key_developments=[
                QuerySummaryPoint(
                    text=f"No matching reported developments were found for {topic} in the last {window}.",
                    evidence_refs=[],
                )
            ],
            uncertainties=[],
            why_it_matters=[],
        )

    top_results = results[:3]
    key_developments = [
        QuerySummaryPoint(
            text=_attributed_claim(item.claim),
            evidence_refs=_refs_for_item(item),
        )
        for item in top_results
    ]

    uncertain_points = [
        QuerySummaryPoint(
            text=_clean_text(item.claim),
            evidence_refs=_refs_for_item(item),
        )
        for item in results
        if _has_uncertainty(item.claim)
    ][:3]
    if not uncertain_points:
        uncertain_points = [
            QuerySummaryPoint(
                text="Several claims in this window remain unconfirmed and should be treated as reported signals.",
                evidence_refs=_refs_for_item(results[0]),
            )
        ]

    why_it_matters = [
        QuerySummaryPoint(
            text=(
                f"This may matter for {topic} monitoring because higher-importance reported changes "
                f"can shift near-term risk and follow-on developments."
            ),
            evidence_refs=_refs_for_item(results[0]),
        )
    ]
    if len(results) > 1:
        why_it_matters.append(
            QuerySummaryPoint(
                text="Multiple reported updates in a short window can indicate momentum, divergence, or unresolved signals.",
                evidence_refs=_refs_for_item(results[1]),
            )
        )

    return QuerySummaryPayload(
        key_developments=key_developments,
        uncertainties=uncertain_points,
        why_it_matters=why_it_matters,
    )


def _can_use_llm(settings: Settings) -> bool:
    model = settings.query_summary_openai_model or settings.openai_model
    return bool(settings.openai_api_key and model)


def _render_prompt(*, topic: str, window: QueryWindow, results: list[QueryNewsResultItem]) -> str:
    serialized_events = [
        {
            "event_ref": f"evt_{item.event_id}",
            "timestamp": item.timestamp,
            "source": item.source,
            "claim": item.claim,
            "category": item.category,
            "importance": item.importance,
            "score": item.score,
            "evidence_refs": item.evidence_refs,
        }
        for item in results
    ]
    allowed_refs = sorted(
        {
            f"evt_{item.event_id}"
            for item in results
        }
        | {ref for item in results for ref in item.evidence_refs}
    )
    events_json = json.dumps(serialized_events, ensure_ascii=True, separators=(",", ":"))
    refs_json = json.dumps(allowed_refs, ensure_ascii=True, separators=(",", ":"))
    return (
        "Summarize reported developments for Telegram users.\n"
        f"Topic: {topic}\n"
        f"Window: {window}\n"
        "Rules:\n"
        "- Keep statements evidence-grounded and concise.\n"
        "- Preserve uncertainty and attribution; do not present claims as verified facts.\n"
        "- Use only evidence_refs from allowed refs.\n"
        '- Return strict JSON with keys: key_developments, uncertainties, why_it_matters; each is a list of {"text":str,"evidence_refs":[str]}.\n'
        f"Allowed refs: {refs_json}\n"
        f"Events: {events_json}\n"
    )


def _validate_llm_payload(
    *,
    raw_text: str,
    results: list[QueryNewsResultItem],
) -> QuerySummaryPayload:
    try:
        payload_obj = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json: {exc.msg}") from exc
    if not isinstance(payload_obj, dict):
        raise ValueError("invalid_json: root must be object")

    try:
        parsed = _StrictSummaryPayload.model_validate(payload_obj)
    except ValidationError as exc:
        raise ValueError(f"schema_error: {exc.errors()[0]['msg']}") from exc

    allowed_refs = (
        {f"evt_{item.event_id}" for item in results}
        | {ref for item in results for ref in item.evidence_refs}
    )
    default_refs = [f"evt_{results[0].event_id}"] if results else []

    def _sanitize(points: list[_StrictPoint]) -> list[QuerySummaryPoint]:
        sanitized: list[QuerySummaryPoint] = []
        for point in points:
            text = _clean_text(point.text)
            if not text:
                continue
            refs: list[str] = []
            for ref in point.evidence_refs:
                if ref in allowed_refs and ref not in refs:
                    refs.append(ref)
            if not refs:
                refs = list(default_refs)
            sanitized.append(QuerySummaryPoint(text=text, evidence_refs=refs[:3]))
        return sanitized

    payload = QuerySummaryPayload(
        key_developments=_sanitize(parsed.key_developments),
        uncertainties=_sanitize(parsed.uncertainties),
        why_it_matters=_sanitize(parsed.why_it_matters),
    )
    if not payload.key_developments:
        raise ValueError("llm payload missing key developments")
    return payload


def _llm_summary_payload(
    *,
    topic: str,
    window: QueryWindow,
    results: list[QueryNewsResultItem],
    settings: Settings,
    llm_client: OpenAiQuerySummaryClient | None = None,
) -> QuerySummaryPayload | None:
    if not results:
        return None
    if llm_client is None:
        if not _can_use_llm(settings):
            return None
        model_name = settings.query_summary_openai_model or settings.openai_model
        if not model_name or not settings.openai_api_key:
            return None
        llm_client = OpenAiQuerySummaryClient(
            api_key=settings.openai_api_key,
            model=model_name,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

    prompt = _render_prompt(topic=topic, window=window, results=results)
    response = llm_client.summarize(prompt)
    return _validate_llm_payload(raw_text=response.raw_text, results=results)


def build_summary_response(
    *,
    news_response: QueryNewsResponse,
    settings: Settings,
    llm_client: OpenAiQuerySummaryClient | None = None,
) -> QuerySummaryResponse:
    try:
        payload = _llm_summary_payload(
            topic=news_response.topic,
            window=news_response.window,
            results=news_response.results,
            settings=settings,
            llm_client=llm_client,
        )
    except (QuerySummaryProviderError, ValueError):
        payload = None

    if payload is None:
        payload = _deterministic_summary(
            topic=news_response.topic,
            window=news_response.window,
            results=news_response.results,
        )

    unique_source_refs = sorted({ref for row in news_response.results for ref in row.evidence_refs})
    return QuerySummaryResponse(
        topic=news_response.topic,
        window=news_response.window,
        generated_at=news_response.generated_at,
        summary=payload,
        source_count=len(unique_source_refs),
    )
