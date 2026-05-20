#!/usr/bin/env python3
"""
Stop hook 전용 — 방금 생성된 노션 턴 로그 페이지에 "턴 원문"을 블록으로 append.

사용법:
  append_turn_raw.py <page_id> <transcript_path> <session_id>

transcript에서 마지막 user 턴 이후 메시지들을 추출해 원문 그대로 노션 블록화.
사용자 발언 + Claude 텍스트 + Claude 도구 호출 목록 포함.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# 같은 폴더의 md_to_notion.py import (hook 배포 시 같이 복사됨)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from md_to_notion import markdown_to_blocks
except ImportError:
    markdown_to_blocks = None  # fallback: raw paragraph


NOTION_VERSION = "2022-06-28"
BLOCK_TEXT_CHUNK = 1900
CHILDREN_PER_REQUEST = 100


def get_token():
    tok = os.environ.get("NOTION_API_TOKEN")
    if tok:
        return tok
    # .env 단일 출처 폴백 (settings.json env 의존 제거)
    env_path = os.path.expanduser("~/.claude/secrets/slack-jipsa.env")
    if os.path.exists(env_path):
        try:
            for line in open(env_path, encoding="utf-8").read().splitlines():
                if line.startswith("NOTION_API_TOKEN="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        return val
        except Exception:
            pass
    # legacy: settings.json env (deprecated, 호환성용)
    settings_path = os.path.expanduser("~/.claude/settings.json")
    if os.path.exists(settings_path):
        try:
            return json.load(open(settings_path))["env"]["NOTION_API_TOKEN"]
        except Exception:
            pass
    return None


def notion_patch(url, body, token):
    req = urllib.request.Request(url, method="PATCH")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    req.data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode("utf-8", "replace")}
    except Exception as e:
        return {"_error": "exception", "_body": str(e)}


def text_to_paragraphs(text):
    blocks = []
    if not text:
        return blocks
    for i in range(0, len(text), BLOCK_TEXT_CHUNK):
        chunk = text[i:i + BLOCK_TEXT_CHUNK]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        })
    return blocks


def heading(text, level=3):
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
    }


def bullet(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
    }


def extract_last_turn(transcript_path):
    """transcript.jsonl에서 마지막 real user 턴 이후 메시지 모두."""
    if not os.path.exists(transcript_path):
        return None

    entries = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue

    # user/assistant만
    msgs = [e for e in entries if e.get("type") in ("user", "assistant")]

    # 마지막 real user 턴 찾기
    last_user_idx = None
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("type") != "user":
            continue
        content = (m.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            last_user_idx = i
            break
        if isinstance(content, list):
            has_text = any(
                isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip()
                for c in content
            )
            if has_text:
                last_user_idx = i
                break

    if last_user_idx is None:
        return None

    turn_msgs = msgs[last_user_idx:]

    user_text = ""
    assistant_texts = []
    tool_calls = []

    for m in turn_msgs:
        t = m.get("type")
        content = (m.get("message") or {}).get("content", [])
        if t == "user" and m is turn_msgs[0]:
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        parts.append(c.get("text", ""))
                user_text = "\n".join(parts).strip()
        elif t == "assistant":
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get("type")
                    if ct == "text":
                        assistant_texts.append(c.get("text", ""))
                    elif ct == "tool_use":
                        name = c.get("name", "?")
                        inp = c.get("input", {})
                        # 도구 파라미터 요약 (긴 건 자름)
                        summary = summarize_tool_input(name, inp)
                        tool_calls.append(f"{name}: {summary}")

    assistant_text = "\n\n".join(t for t in assistant_texts if t.strip()).strip()

    return {
        "user": user_text,
        "assistant": assistant_text,
        "tool_calls": tool_calls,
    }


def summarize_tool_input(name, inp):
    if not isinstance(inp, dict):
        return str(inp)[:200]
    if name == "Write":
        return f"{inp.get('file_path', '?')} ({len(inp.get('content', ''))} B)"
    if name == "Edit":
        return f"{inp.get('file_path', '?')}"
    if name == "Read":
        return f"{inp.get('file_path', '?')}"
    if name == "Bash":
        desc = inp.get("description", "")
        if desc:
            return f"[{desc}]"
        return inp.get("command", "")[:200]
    if name == "Grep":
        return f"pattern={inp.get('pattern', '')} path={inp.get('path', '.')}"
    if name == "Glob":
        return f"pattern={inp.get('pattern', '')}"
    if name == "TodoWrite":
        return f"{len(inp.get('todos', []))} items"
    if name == "Task":
        return f"[{inp.get('subagent_type', '?')}] {inp.get('description', '')}"
    return json.dumps(inp, ensure_ascii=False)[:200]


def _render_md(text):
    """마크다운 파서 있으면 사용, 없으면 plain paragraph fallback."""
    if markdown_to_blocks and text:
        return markdown_to_blocks(text)
    return text_to_paragraphs(text)


def build_blocks(turn):
    blocks = []

    blocks.append(heading("턴 원문", level=2))

    blocks.append(heading(os.environ.get("USER_NAME", "사용자"), level=3))
    if turn["user"]:
        blocks.extend(_render_md(turn["user"]))
    else:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": "(입력 없음)"}}]},
        })

    if turn["tool_calls"]:
        blocks.append(heading("도구 사용", level=3))
        for tc in turn["tool_calls"]:
            blocks.append(bullet(tc))

    if turn["assistant"]:
        blocks.append(heading("Claude", level=3))
        blocks.extend(_render_md(turn["assistant"]))

    return blocks


def main():
    if len(sys.argv) < 3:
        print("Usage: append_turn_raw.py <page_id> <transcript_path> [session_id]", file=sys.stderr)
        sys.exit(1)

    page_id = sys.argv[1]
    transcript_path = sys.argv[2]

    token = get_token()
    if not token:
        print("no NOTION_API_TOKEN", file=sys.stderr)
        sys.exit(0)  # hook이 실패하지 않도록 exit 0

    turn = extract_last_turn(transcript_path)
    if not turn:
        print("no turn extracted", file=sys.stderr)
        sys.exit(0)

    blocks = build_blocks(turn)
    if not blocks:
        sys.exit(0)

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"

    for i in range(0, len(blocks), CHILDREN_PER_REQUEST):
        batch = blocks[i:i + CHILDREN_PER_REQUEST]
        result = notion_patch(url, {"children": batch}, token)
        if result.get("_error"):
            print(f"append error: {result['_error']}: {result.get('_body', '')[:200]}", file=sys.stderr)
            sys.exit(0)
        time.sleep(0.35)

    print(f"appended {len(blocks)} blocks to {page_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
