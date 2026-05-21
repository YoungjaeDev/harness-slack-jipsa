"""슬랙↔클로드 한 턴을 Notion 'Claude Code 턴 로그' DB 에 적재."""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_module1_setup() -> bool:
    """모듈 4는 모듈 1 의존. .env + lib 존재 확인. 누락 시 warning + False.

    인스턴스(글로벌 / 프로젝트) 별로 SECRETS 경로가 다르므로
    SLACK_JIPSA_INSTANCE 환경변수 기반으로 검사 (기본값 = "slack-jipsa").
    """
    instance = os.environ.get("SLACK_JIPSA_INSTANCE", "slack-jipsa")
    required = [
        Path.home() / f".claude/secrets/{instance}.env",
        Path.home() / ".claude/scripts/lib/notion.py",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        logger.warning(
            "모듈 1 미완료. 누락: %s. modules/01-slack-bridge.md 진행 필요", missing,
        )
        return False
    return True


def _get_notion_token() -> str:
    """NOTION_API_TOKEN 우선. legacy NOTION_TOKEN, notion-token.txt 폴백."""
    token = os.environ.get("NOTION_API_TOKEN") or os.environ.get("NOTION_TOKEN") or ""
    if token:
        return token
    legacy = Path.home() / ".claude/secrets/notion-token.txt"
    if legacy.exists():
        return legacy.read_text().strip()
    return ""


def _http(method: str, url: str, headers: dict, data: dict | None = None,
          timeout: int = 15) -> dict:
    raw = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _ensure_daily_page(headers: dict, daily_db: str, date_str: str) -> str | None:
    """일일 통합 페이지 조회 / 없으면 생성. 실패 시 None."""
    if not daily_db:
        return None
    try:
        r = _http(
            "POST",
            f"https://api.notion.com/v1/databases/{daily_db}/query",
            headers,
            {"filter": {"property": "날짜", "date": {"equals": date_str}}, "page_size": 1},
        )
        if r.get("results"):
            return r["results"][0]["id"]
        p = _http(
            "POST",
            "https://api.notion.com/v1/pages",
            headers,
            {
                "parent": {"database_id": daily_db},
                "properties": {
                    "이름": {"title": [{"text": {"content": f"{date_str} 일일 통합"}}]},
                    "날짜": {"date": {"start": date_str}},
                    "상태": {"status": {"name": "진행 중"}},
                    "external_id": {"rich_text": [{"text": {"content": f"daily:{date_str}"}}]},
                },
            },
        )
        return p.get("id")
    except Exception as e:
        logger.warning("daily page setup failed: %s", e)
        return None


def _build_properties(channel: str, event_ts: str, user_text: str, reply_text: str,
                      session_id: str, model: str, bot_name: str,
                      ts_iso: str, daily_id: str | None) -> dict:
    """노션 컬럼 페이로드 빌더 (한국어 컬럼명 유지)."""

    def _trim(s: str, n: int = 1900) -> str:
        return (s or "")[:n]

    # 프로젝트 모드면 PROJECT_DIR (사용자 절대경로) 를, 글로벌이면 기존 daemon 위치를.
    project_dir = os.environ.get("PROJECT_DIR", "").strip()
    instance = os.environ.get("SLACK_JIPSA_INSTANCE", "slack-jipsa")
    cwd_for_log = project_dir or str(Path.home() / f".claude/scripts/{instance}")
    properties = {
        "프로젝트": {"title": [{"text": {"content": f"{bot_name} (슬랙)"}}]},
        "시각": {"date": {"start": ts_iso}},
        "세션 ID": {"rich_text": [{"text": {"content": session_id}}]},
        "작업 디렉토리": {
            "rich_text": [{"text": {"content": cwd_for_log}}],
        },
        "시킨 일": {"rich_text": [{"text": {"content": _trim(user_text)}}]},
        "한 일": {"rich_text": [{"text": {"content": _trim(reply_text)}}]},
        "결과": {"rich_text": [{"text": {"content": _trim(reply_text)}}]},
        "모델": {"select": {"name": model}},
        "도구 호출 수": {"number": 0},
        "전체 요약": {
            "rich_text": [{"text": {"content": _trim((user_text or "") + " → " + (reply_text or ""))}}],
        },
    }
    if daily_id:
        properties["📊 일일 통합"] = {"relation": [{"id": daily_id}]}
    return properties


def notion_log_turn(channel: str, event_ts: str, user_text: str, reply_text: str,
                    session_id: str, model: str,
                    session_db: str, daily_db: str, bot_name: str) -> None:
    """daemon 이 headless 라 Stop hook 발동 안 함 → 직접 적재.

    session_db 가 비어있거나 모듈 1 미완료면 silent skip.
    """
    if not session_db:
        return
    if not verify_module1_setup():
        return
    try:
        # lib.notion 의 upsert_by_external_id 사용 (~/.claude/scripts/lib 가 sys.path 에 있어야 함)
        from lib.notion import upsert_by_external_id

        token = _get_notion_token()
        if not token:
            logger.info("notion log skip: no NOTION_API_TOKEN")
            return
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        ts_iso = now.isoformat()
        date_str = now.date().isoformat()

        daily_id = _ensure_daily_page(headers, daily_db, date_str)
        properties = _build_properties(
            channel, event_ts, user_text, reply_text, session_id, model,
            bot_name, ts_iso, daily_id,
        )

        ext_id = f"jipsa:{channel}:{event_ts}"
        upsert_by_external_id(session_db, ext_id, properties)
    except Exception as e:
        logger.warning("notion log fail: %s", e)
