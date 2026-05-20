#!/usr/bin/env python3
"""Slack ↔ Claude Code daemon entry point.

상세 구조는 jipsa_daemon.py 의 JipsaDaemon 클래스 참고. 본 파일은:
1. .env 로드
2. logging 셋업
3. JipsaDaemon 인스턴스화 + start()
"""
from __future__ import annotations

import sys
from pathlib import Path

# 자기 폴더 + ~/.claude/scripts (lib.notion, lib.slack_mrkdwn 등) import 가능하도록
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.home() / ".claude/scripts"))

from jipsa_daemon import JipsaDaemon  # noqa: E402
from logging_config import configure_logging  # noqa: E402

SECRETS = Path.home() / ".claude/secrets/slack-jipsa.env"
SESSIONS_DIR = Path.home() / ".claude/scripts/slack-jipsa/sessions"
LOGS_DIR = Path.home() / ".claude/scripts/slack-jipsa/logs"
SHARED_DIR = Path.home() / ".claude/scripts/slack-jipsa-shared"


def load_env(secrets: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in secrets.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def build_system_prompt(user_name: str, bot_name: str) -> str:
    return (
        f"당신은 {user_name}님의 슬랙 비서 '{bot_name}'입니다.\n\n"
        f"**환경**: 이 세션은 슬랙 헤드리스(claude --print, 환경변수 SLACK_BOT_TRIGGERED=1)입니다.\n"
        f"사용자 UI 가 없으므로 다음 도구는 절대 호출하지 마세요:\n"
        f"- AskUserQuestion, ExitPlanMode, EnterPlanMode 등 사용자 응답을 기다리는 인터랙티브 도구.\n"
        f"정보가 부족하면 한 줄 질문을 슬랙 답장 텍스트에 담아 {user_name}님의 다음 메시지를 기다리세요.\n"
        f"같은 채널 세션의 다음 turn 이 직전 컨텍스트를 자동 이어받습니다.\n\n"
        f"**필수**: cwd `~/.claude/scripts/slack-jipsa/`의 CLAUDE.md를 절대 규칙으로 따르세요.\n"
        f"페르소나, 슬랙 mrkdwn, 도구 호출 제한, 일정/가계부/캘린더 필터 규칙 모두 거기 있습니다.\n\n"
        f"규칙 어기면 {user_name}님이 직접 지적합니다. 같은 실수 반복 금지."
    )


def main() -> int:
    for d in (SESSIONS_DIR, LOGS_DIR, SHARED_DIR):
        d.mkdir(parents=True, exist_ok=True)

    env = load_env(SECRETS)
    configure_logging(LOGS_DIR, level=env.get("LOG_LEVEL", "INFO"))

    daemon = JipsaDaemon(
        env=env,
        sessions_dir=SESSIONS_DIR,
        logs_dir=LOGS_DIR,
        shared_dir=SHARED_DIR,
        secrets_path=SECRETS,
        system_prompt=build_system_prompt(
            user_name=env.get("USER_NAME", "사용자"),
            bot_name=env.get("SLACK_BOT_NAME", "슬랙 비서"),
        ),
    )
    daemon.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
