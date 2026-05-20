"""슬랙 메시지 필터링: identity (self/user/other-bot) + 토론 키워드 매칭."""
from __future__ import annotations

import re

DISCUSSION_TRIGGER = re.compile(
    r"(토론|비교|반박|의견\s*(나눠|줘|얘기|교환)|각자\s*의견|둘이|서로\s*의견)",
    re.IGNORECASE,
)
DISCUSSION_STOP = re.compile(
    r"(\b그만\b|\b종료\b|\bstop\b|\b끝\b|\b정리\b|\b중단\b|토론\s*그만|토론\s*종료)",
    re.IGNORECASE,
)


def is_self(event: dict, bot_user_id: str) -> bool:
    """봇 자기 메시지인지."""
    return bool(bot_user_id) and event.get("user") == bot_user_id


def is_miri(event: dict, user_slack_id: str) -> bool:
    """대상 사용자 메시지인지."""
    return bool(user_slack_id) and event.get("user") == user_slack_id


def is_other_bot(event: dict, my_bot_user_id: str) -> bool:
    """다른 봇 메시지인지 (subtype=bot_message 인데 내 봇 아님)."""
    if event.get("subtype") != "bot_message":
        return False
    return event.get("user") != my_bot_user_id


def matches_discussion_trigger(text: str | None) -> bool:
    return bool(DISCUSSION_TRIGGER.search(text or ""))


def matches_discussion_stop(text: str | None) -> bool:
    return bool(DISCUSSION_STOP.search(text or ""))
