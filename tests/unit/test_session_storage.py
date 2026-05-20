"""Unit tests for session_storage."""
from __future__ import annotations

import uuid

import session_storage


def test_get_or_create_returns_new_when_missing(tmp_path):
    sessions = tmp_path / "sessions"
    sid, is_new = session_storage.get_or_create_session("Cabc", sessions_dir=sessions)
    assert is_new is True
    uuid.UUID(sid)  # valid UUID
    assert (sessions / "Cabc.txt").read_text().strip() == sid


def test_get_or_create_returns_existing(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "Cabc.txt").write_text("existing-session-id\n")
    sid, is_new = session_storage.get_or_create_session("Cabc", sessions_dir=sessions)
    assert is_new is False
    assert sid == "existing-session-id"


def test_reset_session_creates_new_uuid(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "Cabc.txt").write_text("old-session-id\n")
    new_sid = session_storage.reset_session("Cabc", sessions_dir=sessions)
    assert new_sid != "old-session-id"
    uuid.UUID(new_sid)
    assert (sessions / "Cabc.txt").read_text().strip() == new_sid


def test_session_path_returns_correct_location(tmp_path):
    sessions = tmp_path / "sessions"
    path = session_storage.session_path("CXYZ", sessions_dir=sessions)
    assert path == sessions / "CXYZ.txt"


def test_get_or_create_with_empty_file_creates_new(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "Cabc.txt").write_text("")  # 빈 파일
    sid, is_new = session_storage.get_or_create_session("Cabc", sessions_dir=sessions)
    assert is_new is True
    uuid.UUID(sid)
