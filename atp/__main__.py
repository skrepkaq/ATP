import logging
import os
import sys


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


if __name__ == "__main__":
    setup_logging()
    from .app import main

    main()
