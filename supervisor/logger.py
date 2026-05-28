"""
Onikiri Mk.I — Structured Logger
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_FMT = logging.Formatter(
    fmt="%(asctime)s [%(levelname).1s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def configure_logging(
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> None:
    """
    Configure root logger with a stderr handler (always) and an optional
    rotating file handler writing to <log_dir>/supervisor.log.

    log_dir should be /userdata/logs on a real device.  The directory is
    created if it does not exist.  If creation fails (e.g. /userdata not
    yet mounted), only the stderr handler is registered — the supervisor
    still starts successfully.
    """
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return  # already configured

    # stderr handler — always present
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(_LOG_FMT)
    root.addHandler(stderr_handler)

    # file handler — write to /userdata/logs/supervisor.log
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_dir / "supervisor.log",
                encoding="utf-8",
            )
            file_handler.setFormatter(_LOG_FMT)
            root.addHandler(file_handler)
        except OSError as exc:
            root.warning(
                "Could not open log file in %s (%s) — logging to stderr only",
                log_dir, exc,
            )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"onikiri.{name}")
