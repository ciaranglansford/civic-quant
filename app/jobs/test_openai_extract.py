from __future__ import annotations

import json
import logging
from datetime import datetime

from dotenv import load_dotenv

from ..config import get_settings
from ..services.extraction_llm_client import OpenAiExtractionClient
from ..services.extraction_validation import parse_and_validate_extraction
from ..services.prompt_templates import render_extraction_prompt


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.phase2")


def main() -> None:
    load_dotenv()
    settings = get_settings()
    logger.info(
        "phase2_config phase2_extraction_enabled=%s openai_api_key_present=%s openai_model=%s",
        settings.phase2_extraction_enabled,
        bool(settings.openai_api_key),
        settings.openai_model,
    )

    if not settings.phase2_extraction_enabled:
        raise RuntimeError("PHASE2_EXTRACTION_ENABLED must be true")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    prompt = render_extraction_prompt(
        normalized_text="US CPI rose 0.4% m/m; Treasury yields moved higher and USD strengthened.",
        message_time=datetime.utcnow(),
        source_channel_name="phase2-test",
    )
    client = OpenAiExtractionClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    response = client.extract(prompt.prompt_text)
    validated = parse_and_validate_extraction(response.raw_text)

    print(f"extractor_name={response.extractor_name}")
    print(f"used_openai={response.used_openai}")
    print(f"model={response.model_name}")
    print(f"response_id={response.openai_response_id}")
    print(f"latency={response.latency_ms}")
    print("result_json=")
    print(json.dumps(validated, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
