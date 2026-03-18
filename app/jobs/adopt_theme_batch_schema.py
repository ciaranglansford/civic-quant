from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy import inspect

from ..db import Base, engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.theme_schema")


EXPECTED_TABLES = (
    "theme_runs",
    "event_theme_evidence",
    "theme_opportunity_assessments",
    "thesis_cards",
    "theme_brief_artifacts",
)


def main() -> None:
    load_dotenv()

    # Non-destructive schema adoption: creates missing additive theme tables/indexes.
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(set(EXPECTED_TABLES) - existing)
    if missing:
        raise RuntimeError(
            f"theme schema adoption incomplete; missing tables: {','.join(missing)}"
        )
    logger.info("theme_schema_adoption_complete tables=%s", ",".join(EXPECTED_TABLES))


if __name__ == "__main__":
    main()
