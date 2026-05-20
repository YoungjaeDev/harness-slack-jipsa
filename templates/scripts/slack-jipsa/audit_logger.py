"""Claude `--print` invocation audit log.

Prompt 본문은 저장 안 함 (privacy + 디스크). sha256 hash + 길이만 기록.
session_id + timestamp 로 ~/.claude/projects/<sid>.jsonl 와 cross-reference 가능.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLogger:
    """매 claude_invoke 마다 audit/<date>.log 에 한 줄 append."""

    def __init__(self, audit_dir: Path):
        self.audit_dir = audit_dir
        try:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("audit dir create failed: %s", e)

    def _today_file(self) -> Path:
        return self.audit_dir / f"{time.strftime('%Y-%m-%d')}.log"

    def log_invocation(self, channel: str, session_id: str,
                       prompt: str, result_len: int, status: str) -> None:
        try:
            h = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()[:16]
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            line = (
                f"{ts} channel={channel} session={session_id} "
                f"action=claude_invoke prompt_sha256={h} "
                f"len_in={len(prompt or '')} len_out={result_len} status={status}\n"
            )
            target = self._today_file()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fp:
                fp.write(line)
        except Exception as e:
            logger.warning("audit write failed: %s", e)
