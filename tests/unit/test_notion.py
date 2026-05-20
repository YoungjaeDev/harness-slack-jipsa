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


class TestNotionRequest:
    """notion_request retry / backoff behavior.

    notion_request 는 raise 하지 않고 _error_payload 를 반환한다.
    success: parsed dict. failure: {"_error": True, "method", "path", "status"|"reason", ...}.
    """

    def _http_error(self, code: int, body: bytes = b'{"message":"x"}', retry_after: str | None = None):
        import urllib.error
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        err = urllib.error.HTTPError(
            url="https://api.notion.com/v1/users",
            code=code,
            msg="x",
            hdrs=headers,
            fp=None,
        )
        err.read = lambda: body
        return err

    def test_retries_on_429_then_succeeds(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_test_token_abcdefghij")
        mocker.patch("notion.time.sleep")

        # 1st: 429, 2nd: 200
        mock_200 = mocker.MagicMock()
        mock_200.read.return_value = b'{"results": [], "ok": true}'
        mock_200.status = 200
        cm_200 = mocker.MagicMock()
        cm_200.__enter__ = lambda self: mock_200
        cm_200.__exit__ = lambda *a: False

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise self._http_error(429, retry_after="0")
            return cm_200

        mocker.patch("urllib.request.urlopen", side_effect=side_effect)
        result = notion.notion_request("GET", "/v1/users", max_retries=2)
        assert result.get("ok") is True
        assert call_count[0] == 2

    def test_returns_error_payload_on_400_no_retry(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_test_token_abcdefghij")
        mocker.patch("notion.time.sleep")
        mocker.patch("urllib.request.urlopen", side_effect=self._http_error(400))
        result = notion.notion_request("GET", "/v1/users", max_retries=2)
        assert result.get("_error") is True
        assert result.get("status") == 400

    def test_returns_error_payload_after_max_retries_on_5xx(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_test_token_abcdefghij")
        mocker.patch("notion.time.sleep")
        mocker.patch("urllib.request.urlopen", side_effect=self._http_error(500))
        result = notion.notion_request("GET", "/v1/users", max_retries=1)
        assert result.get("_error") is True
        assert result.get("status") == 500

    def test_token_not_in_logs(self, mocker, monkeypatch, capsys):
        token = "secret_supersecrettokenabcdefghij1234"
        monkeypatch.setenv("NOTION_API_TOKEN", token)
        mocker.patch("notion.time.sleep")
        mocker.patch("urllib.request.urlopen", side_effect=self._http_error(400))
        notion.notion_request("GET", "/v1/users", max_retries=0)
        captured = capsys.readouterr()
        assert token not in captured.err
        assert token not in captured.out
