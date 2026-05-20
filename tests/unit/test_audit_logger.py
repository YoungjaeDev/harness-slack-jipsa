"""Unit tests for audit_logger.AuditLogger."""
from __future__ import annotations

import hashlib

import audit_logger


def test_log_invocation_writes_line(tmp_path):
    audit = audit_logger.AuditLogger(audit_dir=tmp_path)
    audit.log_invocation(
        channel="Cabc", session_id="sess1",
        prompt="hello world", result_len=10, status="ok",
    )
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Cabc" in content
    assert "sess1" in content
    assert "status=ok" in content
    # raw prompt 본문 자체는 포함되지 않음 (privacy)
    assert "hello world" not in content
    # sha256 prefix 포함
    expected_hash = hashlib.sha256(b"hello world").hexdigest()[:16]
    assert expected_hash in content


def test_log_failure_status(tmp_path):
    audit = audit_logger.AuditLogger(audit_dir=tmp_path)
    audit.log_invocation(channel="C1", session_id="s1", prompt="x",
                         result_len=0, status="fail")
    content = next(tmp_path.glob("*.log")).read_text(encoding="utf-8")
    assert "status=fail" in content


def test_audit_dir_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "deeper" / "audit"
    audit = audit_logger.AuditLogger(audit_dir=target)
    audit.log_invocation(channel="C", session_id="s", prompt="p",
                         result_len=1, status="ok")
    assert target.exists()
    assert any(target.glob("*.log"))


def test_log_invocation_swallows_errors(tmp_path, mocker):
    audit = audit_logger.AuditLogger(audit_dir=tmp_path)
    # _today_file 이 던지게 만들고 호출 — 예외 전파 X
    mocker.patch.object(audit, "_today_file", side_effect=OSError("disk full"))
    audit.log_invocation(channel="C", session_id="s", prompt="p",
                         result_len=0, status="ok")  # no raise
