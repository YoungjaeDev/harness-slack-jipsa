"""Unit tests for logging_config."""
from __future__ import annotations

import logging
import logging.handlers

import logging_config


def test_configure_creates_rotating_handler(tmp_path):
    log = logging_config.configure_logging(tmp_path, level="DEBUG", logger_name="t1")
    handlers = [h for h in log.handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].when == "MIDNIGHT"
    assert handlers[0].backupCount == 30


def test_configure_writes_to_daemon_log(tmp_path):
    log = logging_config.configure_logging(tmp_path, logger_name="t2")
    log.info("hello world")
    for h in log.handlers:
        h.flush()
    daemon_log = tmp_path / "daemon.log"
    assert daemon_log.exists()
    content = daemon_log.read_text(encoding="utf-8")
    assert "hello world" in content
    assert "[INFO]" in content


def test_configure_idempotent(tmp_path):
    log1 = logging_config.configure_logging(tmp_path, logger_name="t3")
    handlers_before = len(log1.handlers)
    log2 = logging_config.configure_logging(tmp_path, logger_name="t3")
    assert len(log2.handlers) == handlers_before
    assert log1 is log2


def test_configure_with_custom_backup_days(tmp_path):
    log = logging_config.configure_logging(tmp_path, logger_name="t4", backup_days=7)
    handlers = [h for h in log.handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
    assert handlers[0].backupCount == 7
