"""Logging setup helper for rst_to_md."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "rst_to_md"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the rst_to_md logger.

    Logs are written to stderr so that machine-readable summaries can be
    printed to stdout by the CLI without interleaving.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers on repeated calls (e.g. in tests).
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    return logger
