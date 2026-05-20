"""daemon entry point 단위 테스트: load_env / build_system_prompt / main 흐름."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import daemon as daemon_mod


def test_load_env_parses_simple_kv(tmp_path):
    f = tmp_path / "x.env"
    f.write_text("A=1\nB=hello\n# comment line\nC =  spaced \n")
    env = daemon_mod.load_env(f)
    assert env == {"A": "1", "B": "hello", "C": "spaced"}


def test_load_env_skips_lines_without_equals(tmp_path):
    f = tmp_path / "x.env"
    f.write_text("ONLY_KEY\nA=1\n")
    env = daemon_mod.load_env(f)
    assert env == {"A": "1"}


def test_build_system_prompt_includes_user_and_bot_name():
    s = daemon_mod.build_system_prompt("길동", "비서봇")
    assert "길동" in s
    assert "비서봇" in s
    assert "CLAUDE.md" in s


def test_main_constructs_daemon_and_calls_start(tmp_path, monkeypatch):
    secrets = tmp_path / "slack-jipsa.env"
    secrets.write_text(
        "SLACK_BOT_TOKEN=t\nSLACK_APP_TOKEN=a\nSLACK_CHANNEL=C0\n"
        "USER_NAME=u\nSLACK_BOT_NAME=b\n"
    )
    monkeypatch.setattr(daemon_mod, "SECRETS", secrets)
    monkeypatch.setattr(daemon_mod, "SESSIONS_DIR", tmp_path / "s")
    monkeypatch.setattr(daemon_mod, "LOGS_DIR", tmp_path / "l")
    monkeypatch.setattr(daemon_mod, "SHARED_DIR", tmp_path / "sh")

    fake_daemon = MagicMock()
    with patch.object(daemon_mod, "JipsaDaemon", return_value=fake_daemon), \
         patch.object(daemon_mod, "configure_logging"):
        rc = daemon_mod.main()
    assert rc == 0
    fake_daemon.start.assert_called_once()


def test_main_creates_required_dirs(tmp_path, monkeypatch):
    secrets = tmp_path / "slack-jipsa.env"
    secrets.write_text("SLACK_BOT_TOKEN=t\nSLACK_APP_TOKEN=a\nSLACK_CHANNEL=C0\n")
    monkeypatch.setattr(daemon_mod, "SECRETS", secrets)
    monkeypatch.setattr(daemon_mod, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(daemon_mod, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(daemon_mod, "SHARED_DIR", tmp_path / "shared")
    with patch.object(daemon_mod, "JipsaDaemon"), \
         patch.object(daemon_mod, "configure_logging"):
        daemon_mod.main()
    assert (tmp_path / "sessions").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "shared").is_dir()
