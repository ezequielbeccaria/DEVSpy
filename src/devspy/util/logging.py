"""Thin wrapper over stdlib logging matching DEVSJAVA's `util.Logging` API.

Java has two verbosity levels, `full` and `partial`. We keep those as constants
so ported code reads the same, but route everything through stdlib `logging`.
"""

from __future__ import annotations

import logging

FULL = logging.DEBUG
PARTIAL = logging.INFO

_logger = logging.getLogger("devspy")


def log(message: str, level: int = FULL) -> None:
    _logger.log(level, message)


def is_enabled(level: int = FULL) -> bool:
    return _logger.isEnabledFor(level)


def set_level(level: int) -> None:
    _logger.setLevel(level)


def add_stderr_handler() -> None:
    """Attach a default StreamHandler if no handlers are configured."""
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
