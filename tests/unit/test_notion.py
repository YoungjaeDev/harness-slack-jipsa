"""Unit tests for templates/lib/notion.py."""
from __future__ import annotations

import pytest

import notion  # via conftest sys.path injection


class TestMaskSecrets:
    def test_masks_long_secret_value_in_string(self):
        # secret_ + 20+ chars matches _SECRET_VALUE_RE
        s = "token=secret_abcdefghij1234567890"
        result = notion.mask_secrets(s)
        assert "secret_abcdefghij1234567890" not in result
        assert "[REDACTED]" in result

    def test_masks_xoxb_bot_token(self):
        s = "Bearer xoxb-12345-67890-abcdefghij1234567890"
        result = notion.mask_secrets(s)
        assert "xoxb-" not in result or "[REDACTED]" in result

    def test_preserves_short_non_secret_strings(self):
        assert notion.mask_secrets("hi") == "hi"
        assert notion.mask_secrets("normal text") == "normal text"

    def test_masks_dict_value_by_secret_key(self):
        d = {"Authorization": "anything-goes-here", "ok": True}
        result = notion.mask_secrets(d)
        assert result["Authorization"] == "[REDACTED]"
        assert result["ok"] is True

    def test_masks_dict_value_by_pattern(self):
        d = {"meta": "secret_abcdefghij1234567890", "name": "X"}
        result = notion.mask_secrets(d)
        assert "secret_abcdefghij1234567890" not in str(result["meta"])
        assert result["name"] == "X"

    def test_masks_inside_list(self):
        result = notion.mask_secrets(["secret_abcdefghij1234567890", "harmless"])
        assert "secret_abcdefghij1234567890" not in str(result[0])
        assert result[1] == "harmless"

    def test_masks_nested_structures(self):
        nested = {"outer": {"token": "ntn_abcdefghij1234567890XYZ", "ok": 1}}
        result = notion.mask_secrets(nested)
        assert result["outer"]["token"] == "[REDACTED]"
        assert result["outer"]["ok"] == 1

    def test_handles_none(self):
        assert notion.mask_secrets(None) is None

    def test_handles_integer(self):
        assert notion.mask_secrets(42) == 42

    def test_handles_tuple(self):
        result = notion.mask_secrets(("secret_abcdefghij1234567890", "ok"))
        assert isinstance(result, tuple)
        assert "[REDACTED]" in result[0]
        assert result[1] == "ok"


def test_sanitize_for_waf_is_alias():
    assert notion.sanitize_for_waf("ntn_abcdefghij1234567890XYZ") == "[REDACTED]"
