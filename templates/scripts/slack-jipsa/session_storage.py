"""채널별 Claude Code session_id 저장/조회."""
from __future__ import annotations

import uuid
from pathlib import Path


def session_path(channel: str, sessions_dir: Path) -> Path:
    return sessions_dir / f"{channel}.txt"


def get_or_create_session(channel: str, sessions_dir: Path) -> tuple[str, bool]:
    """채널의 session_id 반환. 없으면 새 UUID 생성. (id, is_new)."""
    p = session_path(channel, sessions_dir)
    if p.exists():
        sid = p.read_text().strip()
        if sid:
            return sid, False
    sid = str(uuid.uuid4())
    sessions_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(sid)
    return sid, True


def reset_session(channel: str, sessions_dir: Path) -> str:
    """세션 리셋. 새 UUID 발급."""
    sid = str(uuid.uuid4())
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path(channel, sessions_dir).write_text(sid)
    return sid
