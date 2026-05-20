"""Unit tests for claude_invoker — Windows cp949 reader thread crash 회귀 방지."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import claude_invoker


def test_run_claude_forces_utf8_decoding():
    """`subprocess.run` 호출에 encoding='utf-8' + errors='replace' 가 들어가야 한다.

    Windows 한국어 locale 의 기본 ANSI 코드페이지(cp949)로 stdout 을 decode
    시도 시 reader thread 가 UnicodeDecodeError 로 죽으면서 r.stdout=None 이
    되어, 호출부는 빈 응답 / SILENT_FAIL 경로로 빠진다. 이를 차단.
    """
    with patch("claude_invoker.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        claude_invoker.run_claude(
            prompt="안녕",
            session_id="11111111-1111-1111-1111-111111111111",
            is_new=True,
            timeout=60,
            system_prompt="test prompt",
        )
        assert mock_run.called
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("text") is True
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"


def test_run_claude_resume_path_also_forces_utf8():
    """resume 경로 (is_new=False, --resume <id>) 도 동일하게 UTF-8."""
    with patch("claude_invoker.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        claude_invoker.run_claude(
            prompt="다시",
            session_id="22222222-2222-2222-2222-222222222222",
            is_new=False,
            timeout=60,
            system_prompt="test prompt",
        )
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
        cmd = mock_run.call_args.args[0]
        assert "--resume" in cmd
        assert "22222222-2222-2222-2222-222222222222" in cmd
