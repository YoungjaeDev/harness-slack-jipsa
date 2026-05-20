"""Unit tests for message filters."""
from __future__ import annotations

import filters


class TestIdentityFilters:
    def test_is_self_true_when_user_matches_bot(self):
        assert filters.is_self({"user": "U0BOT"}, bot_user_id="U0BOT") is True

    def test_is_self_false_for_other_user(self):
        assert filters.is_self({"user": "U0USER"}, bot_user_id="U0BOT") is False

    def test_is_self_false_when_bot_unset(self):
        assert filters.is_self({"user": "U0BOT"}, bot_user_id="") is False

    def test_is_self_false_when_no_user_field(self):
        assert filters.is_self({}, bot_user_id="U0BOT") is False

    def test_is_miri_true_when_user_matches(self):
        assert filters.is_miri({"user": "U0USER"}, user_slack_id="U0USER") is True

    def test_is_miri_false_when_user_differs(self):
        assert filters.is_miri({"user": "U0BOT"}, user_slack_id="U0USER") is False

    def test_is_other_bot_true_for_bot_subtype_different_user(self):
        event = {"subtype": "bot_message", "user": "U0OTHER", "bot_id": "B0OTHER"}
        assert filters.is_other_bot(event, my_bot_user_id="U0BOT") is True

    def test_is_other_bot_false_when_not_bot_message(self):
        event = {"user": "U0USER", "text": "hi"}
        assert filters.is_other_bot(event, my_bot_user_id="U0BOT") is False

    def test_is_other_bot_false_when_my_bot(self):
        event = {"subtype": "bot_message", "user": "U0BOT"}
        assert filters.is_other_bot(event, my_bot_user_id="U0BOT") is False


class TestDiscussionKeywords:
    def test_trigger_matches_basic_phrases(self):
        assert filters.matches_discussion_trigger("둘이 의견 좀 나눠봐")
        assert filters.matches_discussion_trigger("서로 의견 비교해줘")
        assert filters.matches_discussion_trigger("각자 의견 들려줘")
        assert filters.matches_discussion_trigger("토론 시작")

    def test_trigger_no_match_for_normal(self):
        assert not filters.matches_discussion_trigger("오늘 날씨 어때")
        assert not filters.matches_discussion_trigger("저녁 메뉴")

    def test_stop_matches(self):
        assert filters.matches_discussion_stop("그만")
        assert filters.matches_discussion_stop("토론 종료")
        assert filters.matches_discussion_stop("stop")
        # \b 한국어 단어 경계: "정리" 가 단독으로 등장하거나 양옆이 공백/구두점일 때 매치
        assert filters.matches_discussion_stop("이제 정리")

    def test_stop_no_match_for_normal(self):
        assert not filters.matches_discussion_stop("오늘 점심")

    def test_handles_empty_or_none(self):
        assert not filters.matches_discussion_trigger("")
        assert not filters.matches_discussion_trigger(None)
        assert not filters.matches_discussion_stop("")
        assert not filters.matches_discussion_stop(None)
