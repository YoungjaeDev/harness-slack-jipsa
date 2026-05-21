"""notion_logger 단위 테스트: silent skip 조건 + upsert 호출 확인."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import notion_logger


def test_notion_log_silent_when_no_session_db():
    with patch.object(notion_logger, "verify_module1_setup") as mock_verify:
        notion_logger.notion_log_turn(
            channel="C0AAA", event_ts="1.0", user_text="u", reply_text="r",
            session_id="sid", model="opus",
            session_db="", daily_db="", bot_name="bot",
        )
        # session_db 비었으면 verify 호출 전 즉시 return
        mock_verify.assert_not_called()


def test_notion_log_silent_when_module1_missing():
    with patch.object(notion_logger, "verify_module1_setup", return_value=False), \
         patch.object(notion_logger, "_get_notion_token") as mock_tok:
        notion_logger.notion_log_turn(
            channel="C0AAA", event_ts="1.0", user_text="u", reply_text="r",
            session_id="sid", model="opus",
            session_db="db1", daily_db="db2", bot_name="bot",
        )
        # verify False → token 조회까지 가지 않음
        mock_tok.assert_not_called()


def test_notion_log_upsert_called_on_happy_path(monkeypatch):
    fake_upsert = MagicMock()
    fake_module = types.ModuleType("lib.notion")
    fake_module.upsert_by_external_id = fake_upsert
    monkeypatch.setitem(sys.modules, "lib.notion", fake_module)

    with patch.object(notion_logger, "verify_module1_setup", return_value=True), \
         patch.object(notion_logger, "_get_notion_token", return_value="secret_x"), \
         patch.object(notion_logger, "_ensure_daily_page", return_value="daily-id"):
        notion_logger.notion_log_turn(
            channel="C0AAA", event_ts="1.0", user_text="시킨 일", reply_text="한 일",
            session_id="sid-xyz", model="opus",
            session_db="db1", daily_db="db2", bot_name="bot",
        )

    fake_upsert.assert_called_once()
    args = fake_upsert.call_args.args
    assert args[0] == "db1"
    assert args[1].startswith("jipsa:C0AAA:1.0")


def test_verify_module1_setup_returns_false_when_secrets_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(notion_logger.Path, "home", lambda: tmp_path)
    assert notion_logger.verify_module1_setup() is False
