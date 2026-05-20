"""Unit tests for security_monitor.ChannelMemberMonitor."""
from __future__ import annotations

import logging

import security_monitor


def test_baseline_captures_members(mocker):
    web = mocker.MagicMock()
    web.conversations_members.return_value = {"ok": True, "members": ["U1", "U2"]}
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    assert mon.known == {"U1", "U2"}


def test_check_detects_new_member_and_posts_alert(mocker):
    web = mocker.MagicMock()
    web.conversations_members.side_effect = [
        {"members": ["U1"]},
        {"members": ["U1", "U2"]},
    ]
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    mon.check()
    web.chat_postMessage.assert_called_once()
    call_kwargs = web.chat_postMessage.call_args.kwargs
    assert call_kwargs["channel"] == "Cabc"
    assert "U2" in call_kwargs["text"]
    assert mon.known == {"U1", "U2"}


def test_check_no_alert_when_unchanged(mocker):
    web = mocker.MagicMock()
    web.conversations_members.side_effect = [
        {"members": ["U1"]},
        {"members": ["U1"]},
    ]
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    mon.check()
    web.chat_postMessage.assert_not_called()


def test_check_handles_alert_post_failure(mocker):
    web = mocker.MagicMock()
    web.conversations_members.side_effect = [
        {"members": ["U1"]},
        {"members": ["U1", "U2"]},
    ]
    web.chat_postMessage.side_effect = Exception("network down")
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    # should not raise
    mon.check()
    assert mon.known == {"U1", "U2"}
