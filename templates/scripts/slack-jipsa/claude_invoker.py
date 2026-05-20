"""Claude Code CLI 호출 래퍼: subprocess + resume fallback."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable

from session_storage import get_or_create_session, reset_session

logger = logging.getLogger(__name__)


def run_claude(prompt: str, session_id: str, is_new: bool, timeout: int,
               system_prompt: str) -> subprocess.CompletedProcess:
    """claude --print 1회 호출. caller 가 timeout 결정."""
    env = os.environ.copy()
    env["CLAUDE_SKIP_HOOKS"] = "1"
    cmd = [
        "claude", "--print",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--add-dir", str(Path.home()),
        "--output-format", "text",
        "--model", "opus",
        "--append-system-prompt", system_prompt,
    ]
    cmd.extend(["--session-id", session_id] if is_new else ["--resume", session_id])
    cwd = str(Path.home() / ".claude/scripts/slack-jipsa")
    return subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
        env=env, cwd=cwd, timeout=timeout,
    )


def call_claude(prompt: str, channel: str, sessions_dir: Path, system_prompt: str,
                timeout: int,
                on_invoke: Callable[[str, str, int, int], None] | None = None) -> str:
    """클로드 코드 호출. resume 실패 시 새 session 으로 재시도. 결과 string 반환.

    on_invoke(channel, session_id, len_in, len_out): audit hook — Phase E.3.
    """
    sid, is_new = get_or_create_session(channel, sessions_dir)
    try:
        r = run_claude(prompt, sid, is_new, timeout, system_prompt)
        if r.returncode != 0 and not is_new and "No conversation found" in (r.stderr or ""):
            logger.info("resume fail, fallback to new session")
            new_sid = reset_session(channel, sessions_dir)
            r = run_claude(prompt, new_sid, True, timeout, system_prompt)
            sid = new_sid
    except subprocess.TimeoutExpired:
        msg = f"⏱️ 타임아웃 ({timeout}초). 작업이 너무 길어요."
        if on_invoke:
            on_invoke(channel, sid, len(prompt or ""), 0)
        return msg

    out = (r.stdout or "").strip()
    if r.returncode != 0:
        logger.warning("claude fail rc=%d: %s", r.returncode, (r.stderr or "")[-300:])
        if on_invoke:
            on_invoke(channel, sid, len(prompt or ""), 0)
        return "__SILENT_FAIL__"

    if on_invoke:
        on_invoke(channel, sid, len(prompt or ""), len(out))
    return out
