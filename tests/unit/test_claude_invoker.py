"""Unit tests for claude_invoker.

두 갈래 회귀 방지를 한 파일에서 다룸:
- Windows cp949 reader thread crash (subprocess UTF-8 강제 디코딩, env 마커 주입)
- session fallback / timeout / on_invoke 콜백 등 call_claude 행동 계약
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import claude_invoker


# ════════════════════════════════════════════════════════════════════
# run_claude — subprocess 호출 인자 회귀 (Windows cp949 / 헤드리스 마커)
# ════════════════════════════════════════════════════════════════════

def test_run_claude_injects_slack_bot_triggered_env():
    """자식 claude 가 헤드리스 컨텍스트를 감지하도록 SLACK_BOT_TRIGGERED=1 마커 주입."""
    with patch("claude_invoker.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        claude_invoker.run_claude(
            prompt="hi",
            session_id="33333333-3333-3333-3333-333333333333",
            is_new=True,
            timeout=60,
            system_prompt="test",
        )
        env_arg = mock_run.call_args.kwargs.get("env") or {}
        assert env_arg.get("SLACK_BOT_TRIGGERED") == "1"
        assert env_arg.get("CLAUDE_SKIP_HOOKS") == "1"


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


# ════════════════════════════════════════════════════════════════════
# call_claude — session fallback / timeout / on_invoke 계약
# ════════════════════════════════════════════════════════════════════

@pytest.fixture
def sessions_dir(tmp_path):
    d = tmp_path / "sessions"
    d.mkdir()
    return d


def _completed(returncode=0, stdout="응답", stderr=""):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_call_claude_happy_path(sessions_dir):
    with patch.object(claude_invoker, "run_claude", return_value=_completed()) as mock_run:
        out = claude_invoker.call_claude(
            "안녕", "C0AAA", sessions_dir=sessions_dir,
            system_prompt="sys", timeout=30,
        )
    assert out == "응답"
    mock_run.assert_called_once()


def test_call_claude_resume_fallback_creates_new_session(sessions_dir):
    # 기존 session 존재 시뮬: is_new=False 로 첫 호출이 일어남
    (sessions_dir / "C0AAA.txt").write_text("old-sid-1234")
    fail = _completed(returncode=1, stderr="No conversation found for sid")
    ok = _completed(returncode=0, stdout="새 세션 응답")
    with patch.object(claude_invoker, "run_claude", side_effect=[fail, ok]):
        out = claude_invoker.call_claude(
            "안녕", "C0AAA", sessions_dir=sessions_dir,
            system_prompt="sys", timeout=30,
        )
    assert out == "새 세션 응답"
    # session file 이 새 UUID 로 교체됨
    assert (sessions_dir / "C0AAA.txt").read_text() != "old-sid-1234"


def test_call_claude_timeout_returns_friendly_message(sessions_dir):
    with patch.object(
        claude_invoker, "run_claude",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5),
    ):
        out = claude_invoker.call_claude(
            "안녕", "C0AAA", sessions_dir=sessions_dir,
            system_prompt="sys", timeout=5,
        )
    assert "타임아웃" in out
    assert "5" in out


def test_call_claude_nonzero_returns_silent_fail(sessions_dir):
    with patch.object(
        claude_invoker, "run_claude",
        return_value=_completed(returncode=1, stdout="", stderr="some other error"),
    ):
        out = claude_invoker.call_claude(
            "안녕", "C0AAA", sessions_dir=sessions_dir,
            system_prompt="sys", timeout=30,
        )
    assert out == "__SILENT_FAIL__"


def test_call_claude_on_invoke_called_with_lens(sessions_dir):
    seen = {}

    def on_invoke(ch, sid, lin, lout):
        seen.update({"ch": ch, "lin": lin, "lout": lout})

    with patch.object(claude_invoker, "run_claude", return_value=_completed(stdout="abc")):
        claude_invoker.call_claude(
            "hello", "C0AAA", sessions_dir=sessions_dir,
            system_prompt="sys", timeout=30, on_invoke=on_invoke,
        )
    assert seen["ch"] == "C0AAA"
    assert seen["lin"] == 5  # len("hello")
    assert seen["lout"] == 3  # len("abc")
