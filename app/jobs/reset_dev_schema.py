from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from ..db import Base, engine
from .. import models  # noqa: F401


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civicquant.schema")


def main() -> None:
    load_dotenv()
    if os.getenv("CONFIRM_RESET_DEV_SCHEMA", "").lower() != "true":
        raise RuntimeError("Set CONFIRM_RESET_DEV_SCHEMA=true to reset schema")

    logger.warning("reset_dev_schema starting")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.warning("reset_dev_schema complete")


if __name__ == "__main__":
    main()
