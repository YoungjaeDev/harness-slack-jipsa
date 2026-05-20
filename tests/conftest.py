"""pytest fixtures shared across unit and integration tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# templates/lib 와 templates/scripts/slack-jipsa 를 import path 에 추가.
# slack-jipsa/ 안 모듈을 from filters import ... 식으로 직접 import 가능하도록.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "templates" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "templates" / "scripts" / "slack-jipsa"))


@pytest.fixture
def fake_secrets(tmp_path, monkeypatch):
    """Fake ~/.claude/secrets/slack-jipsa.env at a tmp HOME."""
    fake_home = tmp_path / "fake_home"
    secrets_dir = fake_home / ".claude" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    secrets_file = secrets_dir / "slack-jipsa.env"
    secrets_file.write_text(
        "SLACK_BOT_TOKEN=xoxb-fake\n"
        "SLACK_APP_TOKEN=xapp-fake\n"
        "SLACK_CHANNEL=C0FAKE\n"
        "USER_SLACK_ID=U0USER\n"
        "BOT_USER_ID=U0BOT\n"
        "USER_NAME=테스터\n"
        "SLACK_BOT_NAME=테스트봇\n"
        "NOTION_API_TOKEN=secret_fake\n"
        "NOTION_SESSION_DB=db_session\n"
        "NOTION_DAILY_DB=db_daily\n"
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return secrets_file


@pytest.fixture
def mock_web_client(mocker):
    """slack_sdk.WebClient mock with sensible defaults."""
    client = mocker.MagicMock()
    client.auth_test.return_value = {"user_id": "U0BOT", "ok": True}
    client.chat_postMessage.return_value = {"ok": True, "ts": "1700000000.000100"}
    client.conversations_members.return_value = {"ok": True, "members": ["U0USER", "U0BOT"]}
    return client


@pytest.fixture
def fake_transcript(tmp_path):
    """Factory: write ~/.claude/projects/<encoded-cwd>/<session>.jsonl."""
    projects = tmp_path / "fake_home" / ".claude" / "projects" / "fake-cwd"
    projects.mkdir(parents=True, exist_ok=True)

    def factory(session_id: str, lines: list[dict]) -> Path:
        import json
        f = projects / f"{session_id}.jsonl"
        with f.open("w", encoding="utf-8") as fp:
            for line in lines:
                fp.write(json.dumps(line, ensure_ascii=False) + "\n")
        return f

    return factory
