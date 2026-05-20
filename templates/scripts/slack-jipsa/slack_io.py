"""Slack Web API 래퍼: chat.postMessage, reactions.add/remove.

cosmetic 작업 (reaction) 은 실패 시 silent. 본 메시지 게시는 warning 후 None.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def post_message(web, channel: str, text: str,
                 thread_ts: str | None = None,
                 blocks: list[dict] | None = None,
                 mrkdwn: bool = True) -> dict[str, Any] | None:
    """채널에 메시지 게시. 실패 시 warning + None 리턴."""
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text, "mrkdwn": mrkdwn}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks
        return web.chat_postMessage(**kwargs)
    except Exception as e:
        logger.warning("chat_postMessage failed: %s", e)
        return None


def add_reaction(web, channel: str, ts: str, name: str) -> None:
    """이모지 reaction 추가. cosmetic — 실패는 debug 만."""
    try:
        web.reactions_add(channel=channel, timestamp=ts, name=name)
    except Exception as e:
        logger.debug("reactions_add(%s) skipped: %s", name, e)


def remove_reaction(web, channel: str, ts: str, name: str) -> None:
    try:
        web.reactions_remove(channel=channel, timestamp=ts, name=name)
    except Exception as e:
        logger.debug("reactions_remove(%s) skipped: %s", name, e)


def swap_reaction(web, channel: str, ts: str, old: str, new: str) -> None:
    """이전 reaction 제거 + 새 reaction 추가."""
    remove_reaction(web, channel, ts, old)
    add_reaction(web, channel, ts, new)
