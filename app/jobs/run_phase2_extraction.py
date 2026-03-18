from __future__ import annotations

import logging

from dotenv import load_dotenv

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..workflows.phase2_pipeline import process_phase2_batch


logging.basicConfig(level=logging.INFO)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    logging.getLogger("civicquant.phase2").info(
        "phase2_config phase2_extraction_enabled=%s openai_api_key_present=%s openai_model=%s phase2_force_reprocess=%s phase2_content_reuse_enabled=%s phase2_content_reuse_window_hours=%s",
        settings.phase2_extraction_enabled,
        bool(settings.openai_api_key),
        settings.openai_model,
        settings.phase2_force_reprocess,
        settings.phase2_content_reuse_enabled,
        settings.phase2_content_reuse_window_hours,
    )
    init_db()
    with SessionLocal() as db:
        summary = process_phase2_batch(
            db=db,
            settings=settings,
            force_reprocess=settings.phase2_force_reprocess,
        )
        db.commit()
        logging.getLogger("civicquant.phase2").info("phase2_job_summary=%s", summary)


if __name__ == "__main__":
    main()

