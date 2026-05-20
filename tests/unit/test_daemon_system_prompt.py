"""Unit tests for daemon.build_system_prompt — 헤드리스 가드 회귀 방지."""
from __future__ import annotations

import daemon as daemon_mod


def test_system_prompt_forbids_interactive_tools():
    """헤드리스 슬랙 세션에서 인터랙티브 도구 금지 지시가 명시되어야 한다."""
    sp = daemon_mod.build_system_prompt(user_name="테스터", bot_name="잡사")
    # 인터랙티브 도구 이름이 모두 명시되어 있는지
    assert "AskUserQuestion" in sp
    assert "ExitPlanMode" in sp
    assert "EnterPlanMode" in sp
    # 환경 마커 cross-reference
    assert "SLACK_BOT_TRIGGERED" in sp
    # 다음 turn 으로 미루는 fallback 안내
    assert "다음" in sp and ("turn" in sp or "메시지" in sp)


def test_system_prompt_keeps_claude_md_anchor():
    """cwd CLAUDE.md 위임 룰은 그대로 유지되어야 한다 (회귀)."""
    sp = daemon_mod.build_system_prompt(user_name="테스터", bot_name="잡사")
    assert "CLAUDE.md" in sp
