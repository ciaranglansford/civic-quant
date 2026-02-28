from __future__ import annotations

import logging

from dotenv import load_dotenv

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..services.phase2_processing import process_phase2_batch


logging.basicConfig(level=logging.INFO)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    logging.getLogger("civicquant.phase2").info(
        "phase2_config phase2_extraction_enabled=%s openai_api_key_present=%s openai_model=%s",
        settings.phase2_extraction_enabled,
        bool(settings.openai_api_key),
        settings.openai_model,
    )
    init_db()
    with SessionLocal() as db:
        summary = process_phase2_batch(db=db, settings=settings)
        db.commit()
        logging.getLogger("civicquant.phase2").info("phase2_job_summary=%s", summary)


if __name__ == "__main__":
    main()
