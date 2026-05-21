"""slack_io 단위 테스트: post_message + reactions wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock

import slack_io


def test_post_message_returns_response():
    web = MagicMock()
    web.chat_postMessage.return_value = {"ok": True, "ts": "1.0"}
    res = slack_io.post_message(web, "C0AAA", "hi")
    assert res == {"ok": True, "ts": "1.0"}
    web.chat_postMessage.assert_called_once_with(
        channel="C0AAA", text="hi", mrkdwn=True,
    )


def test_post_message_with_thread_ts():
    web = MagicMock()
    web.chat_postMessage.return_value = {"ok": True}
    slack_io.post_message(web, "C0AAA", "hi", thread_ts="1.0")
    kwargs = web.chat_postMessage.call_args.kwargs
    assert kwargs["thread_ts"] == "1.0"


def test_post_message_returns_none_on_exception():
    web = MagicMock()
    web.chat_postMessage.side_effect = RuntimeError("api down")
    assert slack_io.post_message(web, "C0AAA", "hi") is None


def test_add_reaction_silent_on_already_reacted():
    web = MagicMock()
    web.reactions_add.side_effect = RuntimeError("already_reacted")
    # 예외 안 던지고 silent
    slack_io.add_reaction(web, "C0AAA", "1.0", "eyes")


def test_swap_reaction_removes_old_and_adds_new():
    web = MagicMock()
    slack_io.swap_reaction(web, "C0AAA", "1.0", "hourglass", "white_check_mark")
    web.reactions_remove.assert_called_once_with(
        channel="C0AAA", timestamp="1.0", name="hourglass",
    )
    web.reactions_add.assert_called_once_with(
        channel="C0AAA", timestamp="1.0", name="white_check_mark",
    )
