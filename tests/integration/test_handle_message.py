"""Integration tests for JipsaDaemon.handle_message + BOT_USER_ID resolution."""
from __future__ import annotations

import pytest

from jipsa_daemon import JipsaDaemon


def make_env(**overrides) -> dict:
    base = {
        "SLACK_BOT_TOKEN": "xoxb-fake",
        "SLACK_APP_TOKEN": "xapp-fake",
        "SLACK_CHANNEL": "C0FAKE",
        "USER_SLACK_ID": "U0USER",
        "BOT_USER_ID": "U0BOT",
        "USER_NAME": "테스터",
        "SLACK_BOT_NAME": "테스트봇",
        "NOTION_SESSION_DB": "",
        "NOTION_DAILY_DB": "",
        "CLAUDE_TIMEOUT_SEC": "60",
    }
    base.update(overrides)
    return base


@pytest.fixture
def daemon_factory(tmp_path, mocker):
    """팩토리: env override 받아 JipsaDaemon 1개 빌드. WebClient/SocketModeClient mock."""
    mocker.patch("jipsa_daemon.slack_io.make_web_client", autospec=False)
    mocker.patch("jipsa_daemon.SocketModeClient", autospec=False)

    def factory(env_overrides: dict | None = None):
        secrets = tmp_path / "slack-jipsa.env"
        env = make_env(**(env_overrides or {}))
        secrets.write_text("\n".join(f"{k}={v}" for k, v in env.items()))
        sessions_dir = tmp_path / "sessions"
        logs_dir = tmp_path / "logs"
        shared_dir = tmp_path / "shared"
        for d in (sessions_dir, logs_dir, shared_dir):
            d.mkdir(parents=True, exist_ok=True)

        daemon = JipsaDaemon(
            env=env,
            sessions_dir=sessions_dir,
            logs_dir=logs_dir,
            shared_dir=shared_dir,
            secrets_path=secrets,
            system_prompt="test prompt",
        )
        # web 은 mock 으로 갈리지만 MagicMock 메서드 자유 사용
        return daemon, secrets

    return factory


class TestBotUserIdResolve:
    def test_uses_env_when_set(self, daemon_factory):
        daemon, _ = daemon_factory({"BOT_USER_ID": "U0EXPLICIT"})
        assert daemon.bot == "U0EXPLICIT"

    def test_auth_test_fallback_writes_back(self, daemon_factory):
        daemon, secrets = daemon_factory({"BOT_USER_ID": ""})
        daemon.web.auth_test.return_value = {"user_id": "U0AUTOFAKE"}
        # __init__ 안에서 이미 빈 → auth_test 시도. mock 의 기본 return 은 MagicMock 이라
        # bot 이 빈 채로 끝났을 수 있음. 직접 한 번 더 호출.
        new_bot = daemon._resolve_bot_user_id("")
        assert new_bot == "U0AUTOFAKE"
        assert "BOT_USER_ID=U0AUTOFAKE" in secrets.read_text()


class TestHandleMessageRouting:
    def test_self_message_ignored(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude")
        event = {"user": "U0BOT", "channel": "C0FAKE",
                 "text": "self talk", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        call_claude_mock.assert_not_called()

    def test_message_to_unknown_channel_ignored(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude")
        event = {"user": "U0USER", "channel": "C0OTHER",
                 "text": "안녕", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        call_claude_mock.assert_not_called()

    def test_user_message_invokes_claude(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude",
                                        return_value="안녕하세요")
        post_msg = mocker.patch("jipsa_daemon.slack_io.post_message",
                                return_value={"ok": True, "ts": "1.2"})
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "안녕", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        call_claude_mock.assert_called_once()
        post_msg.assert_called()

    def test_reset_keyword_creates_new_session(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        reset_mock = mocker.patch("jipsa_daemon.reset_session",
                                   return_value="new-uuid-xyz")
        call_mock = mocker.patch("jipsa_daemon.call_claude")
        post_msg = mocker.patch("jipsa_daemon.slack_io.post_message")
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "리셋", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        reset_mock.assert_called_once()
        call_mock.assert_not_called()  # 리셋은 claude 호출 안 함

    def test_skip_response_doesnt_post(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        mocker.patch("jipsa_daemon.call_claude", return_value="SKIP")
        post_msg = mocker.patch("jipsa_daemon.slack_io.post_message")
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "메시지", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        post_msg.assert_not_called()

    def test_silent_fail_doesnt_post(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        mocker.patch("jipsa_daemon.call_claude", return_value="__SILENT_FAIL__")
        post_msg = mocker.patch("jipsa_daemon.slack_io.post_message")
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "메시지", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        post_msg.assert_not_called()

    def test_empty_text_ignored(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude")
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "  ", "ts": "1700000000.000100"}
        daemon.handle_message(event)
        call_claude_mock.assert_not_called()


class TestDiscussionMode:
    def test_trigger_enables_mode(self, daemon_factory, mocker):
        daemon, _ = daemon_factory({"SLACK_CHANNEL_DIALOG": "C0DLG"})
        mocker.patch("jipsa_daemon.call_claude", return_value="discussion reply")
        mocker.patch("jipsa_daemon.slack_io.post_message", return_value={"ok": True, "ts": "1.2"})
        event = {"user": "U0USER", "channel": "C0DLG",
                 "text": "둘이 의견 나눠봐", "ts": "1700000000.000200"}
        daemon.handle_message(event)
        assert daemon.discussion_mode.get("C0DLG") is True

    def test_stop_keyword_disables_mode(self, daemon_factory, mocker):
        daemon, _ = daemon_factory({"SLACK_CHANNEL_DIALOG": "C0DLG"})
        daemon.discussion_mode["C0DLG"] = True
        mocker.patch("jipsa_daemon.call_claude", return_value="ok")
        mocker.patch("jipsa_daemon.slack_io.post_message", return_value={"ok": True, "ts": "1.2"})
        event = {"user": "U0USER", "channel": "C0DLG",
                 "text": "그만", "ts": "1700000000.000300"}
        daemon.handle_message(event)
        assert daemon.discussion_mode.get("C0DLG") is False
