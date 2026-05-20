"""Unit tests for templates/lib/md_to_notion.py."""
from __future__ import annotations

import md_to_notion


def _types(blocks):
    return [b["type"] for b in blocks]


def test_empty_string_returns_empty():
    assert md_to_notion.markdown_to_blocks("") == []


def test_paragraph():
    blocks = md_to_notion.markdown_to_blocks("간단한 텍스트.")
    assert len(blocks) >= 1
    assert _types(blocks) == ["paragraph"]


def test_heading_levels():
    blocks = md_to_notion.markdown_to_blocks("# H1\n\n## H2\n\n### H3\n\n#### H4")
    types = _types(blocks)
    assert "heading_1" in types
    assert "heading_2" in types
    # H4 이상은 heading_3 으로 clamp (markdown_to_blocks 의 min(3, level))
    assert types.count("heading_3") == 2


def test_bullet_list():
    blocks = md_to_notion.markdown_to_blocks("- item1\n- item2\n- item3")
    types = _types(blocks)
    assert types.count("bulleted_list_item") == 3


def test_numbered_list():
    blocks = md_to_notion.markdown_to_blocks("1. one\n2. two\n3. three")
    types = _types(blocks)
    assert types.count("numbered_list_item") == 3


def test_code_block_language_preserved():
    md = "```python\nprint('x')\nx = 1\n```"
    blocks = md_to_notion.markdown_to_blocks(md)
    code = [b for b in blocks if b["type"] == "code"]
    assert len(code) == 1
    assert code[0]["code"]["language"] == "python"


def test_quote():
    blocks = md_to_notion.markdown_to_blocks("> 인용한 줄\n> 두 번째 줄")
    types = _types(blocks)
    assert "quote" in types


def test_divider():
    blocks = md_to_notion.markdown_to_blocks("이전\n\n---\n\n다음")
    types = _types(blocks)
    assert "divider" in types


def test_long_paragraph_chunked_under_2000():
    long = "가" * 5000
    blocks = md_to_notion.markdown_to_blocks(long)
    # 모든 paragraph 의 rich_text content 가 2000 이하
    for b in blocks:
        if b["type"] != "paragraph":
            continue
        for rt in b["paragraph"]["rich_text"]:
            if rt.get("type") == "text":
                assert len(rt["text"]["content"]) <= 2000


def test_max_blocks_truncation():
    md = "\n\n".join(f"para {i}" for i in range(20))
    blocks = md_to_notion.markdown_to_blocks(md, max_blocks=5)
    # 5 paragraph + 1 "이하 생략" 추가 = 6 blocks
    assert len(blocks) == 6
    # 마지막 블록은 "이하 생략" 안내
    last = blocks[-1]
    assert last["type"] == "paragraph"


def test_inline_formatting_does_not_crash():
    md = "**굵게** 일반 *기울임* `코드` [링크](https://example.com)"
    blocks = md_to_notion.markdown_to_blocks(md)
    assert len(blocks) >= 1
    assert blocks[0]["type"] == "paragraph"
