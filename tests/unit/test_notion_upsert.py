"""Unit tests for upsert_by_external_id idempotency."""
from __future__ import annotations

import pytest

import notion


@pytest.fixture(autouse=True)
def reset_data_source_cache():
    """_DATA_SOURCE_CACHE 는 모듈 글로벌 — 테스트 간 격리 위해 매번 비움."""
    notion._DATA_SOURCE_CACHE.clear()
    yield
    notion._DATA_SOURCE_CACHE.clear()


class TestUpsertByExternalId:
    def test_requires_external_id(self):
        with pytest.raises(ValueError):
            notion.upsert_by_external_id("db1", "", {"name": "X"})
        with pytest.raises(ValueError):
            notion.upsert_by_external_id("db1", "   ", {"name": "X"})

    def test_creates_new_page_when_not_exists(self, mocker):
        # _resolve_data_source_id → db_id (단일 source 가정)
        # query_by_external_id → None (없음)
        # notion_request POST pages → 새 페이지 dict
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            # _resolve_data_source_id 의 GET databases/db1
            {"data_sources": [{"id": "db1"}]},
            # query_by_external_id 내부 query_database 호출 (data_source query)
            {"results": []},
            # POST pages
            {"id": "page_new", "object": "page"},
        ]
        result = notion.upsert_by_external_id(
            db_id="db1",
            external_id="ext_1",
            properties={"이름": {"title": [{"text": {"content": "X"}}]}},
        )
        assert result["id"] == "page_new"
        # 마지막 호출은 POST pages
        last = nreq.call_args_list[-1]
        assert last.args[0] == "POST"
        assert last.args[1] == "pages"

    def test_updates_when_exists(self, mocker):
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            # _resolve_data_source_id
            {"data_sources": [{"id": "db1"}]},
            # query — 기존 row 발견
            {"results": [{"id": "page_existing"}]},
            # PATCH
            {"id": "page_existing", "object": "page"},
        ]
        result = notion.upsert_by_external_id(
            db_id="db1",
            external_id="ext_1",
            properties={"제목": {"title": [{"text": {"content": "Y"}}]}},
        )
        assert result["id"] == "page_existing"
        assert result["_upsert"] == "updated"
        # 두 번째 (PATCH) 호출 검증
        patch_call = nreq.call_args_list[-1]
        assert patch_call.args[0] == "PATCH"
        assert "page_existing" in patch_call.args[1]

    def test_children_only_on_first_insert(self, mocker):
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            {"data_sources": [{"id": "db1"}]},
            {"results": []},  # no existing
            {"id": "page_new"},
        ]
        notion.upsert_by_external_id(
            db_id="db1",
            external_id="ext_1",
            properties={"이름": {"title": [{"text": {"content": "X"}}]}},
            children=[{"type": "paragraph"}],
        )
        post_call = nreq.call_args_list[-1]
        body = post_call.args[2]
        assert "children" in body
        assert body["children"] == [{"type": "paragraph"}]

    def test_children_not_sent_on_update(self, mocker):
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            {"data_sources": [{"id": "db1"}]},
            {"results": [{"id": "page_existing"}]},
            {"id": "page_existing"},
        ]
        notion.upsert_by_external_id(
            db_id="db1",
            external_id="ext_1",
            properties={"이름": {"title": [{"text": {"content": "X"}}]}},
            children=[{"type": "paragraph"}],
        )
        # PATCH body 에는 children 없음 (idempotency)
        patch_call = nreq.call_args_list[-1]
        body = patch_call.args[2]
        assert "children" not in body
