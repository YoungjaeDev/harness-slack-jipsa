"""Centralized logging setup: TimedRotatingFileHandler + console."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def configure_logging(log_dir: Path, level: str = "INFO",
                       logger_name: str = "jipsa", backup_days: int = 30) -> logging.Logger:
    """daemon logger 셋업. 파일은 자정 회전, 30일치 유지."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "daemon.log",
        when="midnight",
        backupCount=backup_days,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger(logger_name)
    if not root.handlers:
        root.addHandler(handler)
        root.addHandler(console)
    root.setLevel(level)
    root.propagate = False
    return root
