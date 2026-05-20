"""shared_buffer: cross-bot conversation buffer 단위 테스트."""
from __future__ import annotations

import shared_buffer


def test_path_uses_channel_and_thread(tmp_path):
    p = shared_buffer.path(tmp_path, "C0AAA", "1700000000.001")
    assert p.parent == tmp_path
    assert "C0AAA" in p.name
    assert "1700000000.001" in p.name
    assert p.suffix == ".jsonl"


def test_path_root_when_no_thread(tmp_path):
    p = shared_buffer.path(tmp_path, "C0AAA")
    assert "root" in p.name


def test_load_returns_empty_for_missing_file(tmp_path):
    assert shared_buffer.load(tmp_path, "C0AAA", "") == []


def test_append_then_load_roundtrip(tmp_path):
    shared_buffer.append(tmp_path, "C0AAA", "", "user", "hi", msg_ts="ts1")
    shared_buffer.append(tmp_path, "C0AAA", "", "bot", "yo", msg_ts="ts2")
    rows = shared_buffer.load(tmp_path, "C0AAA", "")
    assert [r["who"] for r in rows] == ["user", "bot"]
    assert [r["text"] for r in rows] == ["hi", "yo"]
    assert [r["msg_ts"] for r in rows] == ["ts1", "ts2"]


def test_append_dedupes_by_msg_ts(tmp_path):
    shared_buffer.append(tmp_path, "C0AAA", "", "user", "hi", msg_ts="ts1")
    shared_buffer.append(tmp_path, "C0AAA", "", "user", "hi-dup", msg_ts="ts1")
    rows = shared_buffer.load(tmp_path, "C0AAA", "")
    assert len(rows) == 1
    assert rows[0]["text"] == "hi"


def test_load_respects_limit(tmp_path):
    for i in range(50):
        shared_buffer.append(tmp_path, "C0AAA", "", "u", f"m{i}", msg_ts=f"ts{i}")
    rows = shared_buffer.load(tmp_path, "C0AAA", "", limit=10)
    assert len(rows) == 10
    assert rows[-1]["text"] == "m49"
