"""JipsaDaemon helper method 단위 테스트.

JipsaDaemon 을 정상 인스턴스화하려면 slack_sdk 외부 호출이 필요해서
_construct factory 가 외부 의존을 mock 으로 채워준 객체를 만든다.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import jipsa_daemon as jd
from jipsa_daemon import JipsaDaemon


def _construct(tmp_path, mock_web):
    env = {
        "SLACK_BOT_TOKEN": "xoxb-fake",
        "SLACK_APP_TOKEN": "xapp-fake",
        "SLACK_CHANNEL": "C0MAIN",
        "SLACK_CHANNEL_DIALOG": "C0DIAL",
        "USER_SLACK_ID": "U0USER",
        "BOT_USER_ID": "U0BOT",
        "USER_NAME": "테스터",
        "SLACK_BOT_NAME": "테스트봇",
    }
    with patch.object(jd, "WebClient", return_value=mock_web), \
         patch.object(jd, "SocketModeClient", return_value=MagicMock()), \
         patch.object(jd, "AuditLogger", return_value=MagicMock()), \
         patch.object(jd, "ChannelMemberMonitor", return_value=MagicMock()):
        d = JipsaDaemon(
            env=env,
            sessions_dir=tmp_path / "sessions",
            logs_dir=tmp_path / "logs",
            shared_dir=tmp_path / "shared",
            secrets_path=tmp_path / "secrets.env",
            system_prompt="sys",
        )
    return d


@pytest.fixture
def daemon(tmp_path, mock_web_client):
    return _construct(tmp_path, mock_web_client)


# ---- _apply_filters ----

def test_apply_filters_drops_empty_text(daemon):
    assert daemon._apply_filters({"text": "", "channel": "C0MAIN", "user": "U0USER"}) is None


def test_apply_filters_drops_other_channel(daemon):
    ev = {"text": "hi", "channel": "C9OTHER", "user": "U0USER", "ts": "1.0"}
    assert daemon._apply_filters(ev) is None


def test_apply_filters_drops_self(daemon):
    ev = {"text": "hi", "channel": "C0MAIN", "user": "U0BOT", "ts": "1.0"}
    assert daemon._apply_filters(ev) is None


def test_apply_filters_passes_miri_in_main(daemon):
    ev = {"text": "hi", "channel": "C0MAIN", "user": "U0USER", "ts": "1.0"}
    result = daemon._apply_filters(ev)
    assert result is not None
    is_dialog, ctx = result
    assert is_dialog is False
    assert ctx["is_miri"] is True
    assert ctx["text"] == "hi"


# ---- _toggle_discussion ----

def test_toggle_discussion_stop_keyword(daemon):
    daemon.discussion_mode["C0DIAL"] = True
    daemon._toggle_discussion("C0DIAL", "토론 그만")
    assert daemon.discussion_mode["C0DIAL"] is False


def test_toggle_discussion_trigger_keyword(daemon):
    daemon._toggle_discussion("C0DIAL", "다같이 토론해줘")
    assert daemon.discussion_mode["C0DIAL"] is True
    assert daemon.dialog_self_turn_count == 0


def test_toggle_discussion_new_topic_turns_off(daemon):
    daemon.discussion_mode["C0DIAL"] = True
    daemon.dialog_self_turn_count = 3
    daemon._toggle_discussion("C0DIAL", "오늘 날씨가 좋다")
    assert daemon.discussion_mode["C0DIAL"] is False
    assert daemon.dialog_self_turn_count == 0


# ---- _check_other_bot_continue ----

def test_other_bot_continue_false_when_discussion_off(daemon):
    daemon.discussion_mode["C0DIAL"] = False
    assert daemon._check_other_bot_continue("C0DIAL") is False


def test_other_bot_continue_false_at_turn_limit(daemon):
    daemon.discussion_mode["C0DIAL"] = True
    daemon.dialog_self_turn_count = daemon.DIALOG_TURN_LIMIT
    assert daemon._check_other_bot_continue("C0DIAL") is False
    assert daemon.discussion_mode["C0DIAL"] is False


def test_other_bot_continue_true_when_under_limit(daemon):
    daemon.discussion_mode["C0DIAL"] = True
    daemon.dialog_self_turn_count = 1
    assert daemon._check_other_bot_continue("C0DIAL") is True


# ---- _build_prompt ----

def test_build_prompt_no_ctx_when_buffer_empty(daemon):
    result = daemon._build_prompt("C0MAIN", "", "현재 메시지")
    assert result == "현재 메시지"


def test_build_prompt_adds_ctx_when_buffer_has_history(daemon):
    import shared_buffer
    daemon.shared_dir.mkdir(parents=True, exist_ok=True)
    shared_buffer.append(daemon.shared_dir, "C0MAIN", "", "테스터", "예전 발화", msg_ts="ts1")
    shared_buffer.append(daemon.shared_dir, "C0MAIN", "", "클코", "예전 응답", msg_ts="ts2")
    result = daemon._build_prompt("C0MAIN", "", "현재 메시지")
    assert "최근 대화 맥락" in result
    assert "현재 메시지" in result
    assert "예전 발화" in result


# ---- _handle_reply ----

def test_handle_reply_skip_branch(daemon, mock_web_client):
    out = daemon._handle_reply("C0MAIN", "1.0", "", "SKIP because other bot's turn")
    assert out is None
    mock_web_client.chat_postMessage.assert_not_called()


def test_handle_reply_silent_fail_branch(daemon, mock_web_client):
    out = daemon._handle_reply("C0MAIN", "1.0", "", "__SILENT_FAIL__")
    assert out is None
    mock_web_client.chat_postMessage.assert_not_called()


def test_handle_reply_normal_branch_posts_and_returns_clean_text(daemon, mock_web_client):
    out = daemon._handle_reply("C0MAIN", "1.0", "", "정상 응답입니다")
    mock_web_client.chat_postMessage.assert_called_once()
    called = mock_web_client.chat_postMessage.call_args
    assert called.kwargs["channel"] == "C0MAIN"
    assert "정상 응답입니다" in called.kwargs["text"]
    # thread_ts 가 빈 문자열이면 post_message 호출에 None 또는 미전달.
    assert called.kwargs.get("thread_ts") in (None, "")
    # to_mrkdwn 변환된 텍스트가 리턴되어야 Notion 적재본과 슬랙 본문이 일치
    assert isinstance(out, str)
    assert "정상 응답입니다" in out


def test_handle_reply_threaded_message_replies_in_same_thread(daemon, mock_web_client):
    """thread_ts 가 있으면 post_message 에 그대로 전달되어 같은 스레드에 답글.

    회귀 방지: 직전 구조에서 thread_ts 인자를 받기만 하고 post_message 에
    전달하지 않아 스레드 응답이 채널 루트로 빠지던 버그.
    """
    daemon._handle_reply("C0MAIN", "1.5", "1700000000.000050", "스레드 응답")
    called = mock_web_client.chat_postMessage.call_args
    assert called.kwargs.get("thread_ts") == "1700000000.000050"


def test_handle_reply_returns_none_when_post_fails(daemon, mock_web_client, mocker):
    """post_message 가 falsy 면 Slack 에 안 올라간 것이므로 _handle_reply 가
    None 반환 + warning reaction. 호출자는 shared_buffer / Notion 기록을 건너뜀.

    회귀 방지: 직전 구조에서 res falsy 라도 white_check_mark 로 swap 하고
    reply_clean 을 리턴해 Slack/Notion 기록 불일치.
    """
    # slack_io.post_message 가 None 리턴하도록 직접 patch (실제 web mock 이
    # 예외/falsy 를 흉내내는 것보다 명시적).
    mocker.patch(
        "jipsa_daemon.slack_io.post_message",
        return_value=None,
    )
    swap_spy = mocker.patch("jipsa_daemon.slack_io.swap_reaction")

    out = daemon._handle_reply("C0MAIN", "1.0", "", "응답")

    assert out is None
    swap_spy.assert_called_once()
    args = swap_spy.call_args.args
    # swap_reaction(web, channel, ts, from_name, to_name) 의 to_name 이 "warning"
    assert args[-1] == "warning"
