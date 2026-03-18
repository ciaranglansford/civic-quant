"""Prompt template loader/renderer for digest synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROMPT_VERSION = "digest_synthesis_v1"
_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"


@dataclass(frozen=True)
class RenderedDigestPrompt:
    prompt_version: str
    prompt_text: str


def render_digest_synthesis_prompt(
    *,
    source_candidates_json: str,
    top_developments_limit: int,
    section_bullet_limit: int,
    known_topic_labels_csv: str,
) -> RenderedDigestPrompt:
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"missing prompt template: {_TEMPLATE_PATH}")

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = (
        template.replace("{{source_candidates_json}}", source_candidates_json)
        .replace("{{top_developments_limit}}", str(top_developments_limit))
        .replace("{{section_bullet_limit}}", str(section_bullet_limit))
        .replace("{{known_topic_labels_csv}}", known_topic_labels_csv)
    )

    required = (
        "source_candidates_json",
        "top_developments_limit",
        "section_bullet_limit",
        "known_topic_labels_csv",
    )
    missing = [field for field in required if f"{{{{{field}}}}}" in rendered]
    if missing:
        raise ValueError(f"template placeholders not replaced: {missing}")

    return RenderedDigestPrompt(prompt_version=PROMPT_VERSION, prompt_text=rendered)
