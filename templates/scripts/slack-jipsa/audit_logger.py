"""Claude invocation audit log — Phase E.3 본구현 예정. 현재 noop stub."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLogger:
    """Phase E.3 에서 sha256 hash + 길이 기록 본구현 예정. 현재 noop."""

    def __init__(self, audit_dir: Path):
        self.audit_dir = audit_dir

    def log_invocation(self, channel: str, session_id: str,
                       prompt: str, result_len: int, status: str) -> None:
        pass
