"""Cross-bot conversation buffer. msg_ts dedup + (Unix) fcntl 잠금.

stateless 순수 함수 모듈. JipsaDaemon 외 다른 모듈에서도 재사용 가능.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

try:
    import fcntl  # type: ignore
except ImportError:
    fcntl = None  # type: ignore

logger = logging.getLogger(__name__)

SHARED_BUFFER_LIMIT = 30


def path(shared_dir: Path, channel: str, thread_ts: str = "") -> Path:
    key = f"slack_{channel}_{thread_ts or 'root'}"
    return shared_dir / f"{key}.jsonl"


def load(shared_dir: Path, channel: str, thread_ts: str = "",
         limit: int = SHARED_BUFFER_LIMIT) -> list[dict]:
    p = path(shared_dir, channel, thread_ts)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def append(shared_dir: Path, channel: str, thread_ts: str,
           who: str, text: str, msg_ts: str = "") -> None:
    """msg_ts 같은 기존 항목 있으면 적재 skip. Unix fcntl 가용 시 잠금."""
    p = path(shared_dir, channel, thread_ts)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "msg_ts": msg_ts,
        "who": who,
        "text": (text or "")[:2000],
    }
    try:
        with p.open("a+", encoding="utf-8") as f:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                if msg_ts:
                    f.seek(0)
                    for line in f.read().splitlines()[-50:]:
                        try:
                            if json.loads(line).get("msg_ts") == msg_ts:
                                return
                        except Exception:
                            pass
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.warning("append failed: %s", e)
