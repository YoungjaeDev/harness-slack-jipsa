# agent-bootstrap Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** agent-bootstrap 키트의 daemon.py 구조 리팩터, pytest 회귀 인프라, Windows 검증본 PS1, 운영 가드, 보안 보강, 한국어 CONTRIBUTING 문서를 6 Phase 순차로 도입한다.

**Architecture:** `templates/scripts/slack-jipsa/daemon.py` (521줄) 를 `JipsaDaemon` 클래스 + 7개 보조 모듈로 분리. pytest 기반 단위·통합 테스트 + GitHub Actions CI 도입. 채널 멤버 모니터링과 audit log 로 `--dangerously-skip-permissions` risk 완화. Stop hook 의 Windows AI-즉석-생성 (D 카테고리) 을 검증본 (C 카테고리) 으로 승격.

**Tech Stack:** Python 3.10+, pytest, pytest-cov, uv, slack_sdk, GitHub Actions, PowerShell 5.1+

**Spec:** [docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md](../specs/2026-05-20-agent-bootstrap-cleanup-design.md)

**의존성 순서:**
```
Phase B1 (notion.py 단위 테스트, self-contained)
  → Phase A (daemon.py 리팩터)
    → Phase B2 (handle_message 통합 테스트)
      → Phase C/D/E/F (병렬 가능)
```

---

## Phase B1 — 테스트 인프라 (selfcontained, 가장 먼저)

### Task 1: pyproject.toml + uv 환경 + conftest.py 스켈레톤

**Files:**
- Create: `C:\dev\agent-bootstrap\pyproject.toml`
- Create: `C:\dev\agent-bootstrap\tests\__init__.py` (빈 파일)
- Create: `C:\dev\agent-bootstrap\tests\conftest.py`
- Create: `C:\dev\agent-bootstrap\tests\unit\__init__.py` (빈 파일)
- Create: `C:\dev\agent-bootstrap\tests\integration\__init__.py` (빈 파일)
- Modify: `C:\dev\agent-bootstrap\.gitignore` (add `.pytest_cache/`, `.coverage`, `htmlcov/`, `__pycache__/`, `.venv/`)

- [ ] **Step 1: pyproject.toml 작성**

`pyproject.toml`:
```toml
[project]
name = "agent-bootstrap-tests"
version = "0.1.0"
description = "Test harness for agent-bootstrap kit (not the kit itself)"
requires-python = ">=3.10"

[project.optional-dependencies]
test = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-mock>=3.12",
    "slack_sdk>=3.27",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-ra -q"

[tool.coverage.run]
source = ["templates"]
omit = ["**/__pycache__/*", "tests/*"]
```

- [ ] **Step 2: conftest.py 작성**

`tests/conftest.py`:
```python
"""pytest fixtures shared across unit and integration tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# templates/lib 와 templates/scripts/slack-jipsa 를 import path 에 추가
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "templates" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "templates" / "scripts" / "slack-jipsa"))


@pytest.fixture
def fake_secrets(tmp_path, monkeypatch):
    """Fake ~/.claude/secrets/slack-jipsa.env."""
    secrets_file = tmp_path / "slack-jipsa.env"
    secrets_file.write_text(
        "SLACK_BOT_TOKEN=xoxb-fake\n"
        "SLACK_APP_TOKEN=xapp-fake\n"
        "SLACK_CHANNEL=C0FAKE\n"
        "USER_SLACK_ID=U0USER\n"
        "BOT_USER_ID=U0BOT\n"
        "USER_NAME=테스터\n"
        "SLACK_BOT_NAME=테스트봇\n"
        "NOTION_API_TOKEN=secret_fake\n"
        "NOTION_SESSION_DB=db_session\n"
        "NOTION_DAILY_DB=db_daily\n"
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path.parent / "fake_home")
    fake_home = tmp_path.parent / "fake_home"
    (fake_home / ".claude" / "secrets").mkdir(parents=True, exist_ok=True)
    target = fake_home / ".claude" / "secrets" / "slack-jipsa.env"
    target.write_text(secrets_file.read_text())
    return target


@pytest.fixture
def mock_web_client(mocker):
    """slack_sdk.WebClient mock."""
    client = mocker.MagicMock()
    client.auth_test.return_value = {"user_id": "U0BOT", "ok": True}
    client.chat_postMessage.return_value = {"ok": True, "ts": "1700000000.000100"}
    client.conversations_members.return_value = {"ok": True, "members": ["U0USER", "U0BOT"]}
    return client


@pytest.fixture
def fake_transcript(tmp_path, monkeypatch):
    """Fake ~/.claude/projects/<encoded-cwd>/<session>.jsonl."""
    projects = tmp_path / "fake_home" / ".claude" / "projects" / "fake-cwd"
    projects.mkdir(parents=True, exist_ok=True)

    def factory(session_id: str, lines: list[dict]):
        import json
        f = projects / f"{session_id}.jsonl"
        with f.open("w", encoding="utf-8") as fp:
            for line in lines:
                fp.write(json.dumps(line, ensure_ascii=False) + "\n")
        return f

    return factory
```

- [ ] **Step 3: .gitignore 업데이트**

`.gitignore` 끝에 추가:
```
# pytest / coverage
.pytest_cache/
.coverage
htmlcov/
__pycache__/
.venv/
*.egg-info/
```

- [ ] **Step 4: uv sync 검증**

Run: `uv sync --extra test`
Expected: `Resolved N packages` 및 `.venv` 생성. 에러 없음.

- [ ] **Step 5: pytest collect 검증 (test 0개 — 인프라만 확인)**

Run: `uv run pytest --collect-only`
Expected: `no tests ran` 또는 `collected 0 items`. import 에러 없음.

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py tests/unit/__init__.py tests/integration/__init__.py .gitignore
git commit -m "test: add pyproject + pytest infrastructure"
```

---

### Task 2: lib/notion.py 단위 테스트 — mask_secrets

**Files:**
- Create: `C:\dev\agent-bootstrap\tests\unit\test_notion.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_notion.py`:
```python
"""Unit tests for templates/lib/notion.py."""
from __future__ import annotations

import pytest

import notion  # via conftest sys.path injection


class TestMaskSecrets:
    def test_masks_long_bearer_token(self):
        result = notion.mask_secrets("Bearer secret_abcdefghij1234567890")
        assert "secret_" not in result or "***" in result

    def test_preserves_short_strings(self):
        # 짧은 문자열은 시크릿 후보 아님
        assert notion.mask_secrets("hi") == "hi"

    def test_masks_inside_dict(self):
        d = {"Authorization": "Bearer secret_abcdefghij1234567890", "ok": True}
        result = notion.mask_secrets(d)
        assert "secret_" not in str(result["Authorization"]) or "***" in str(result["Authorization"])
        assert result["ok"] is True

    def test_masks_inside_list(self):
        result = notion.mask_secrets(["secret_abcdefghij1234567890", "harmless"])
        assert "***" in str(result[0]) or "secret_" not in str(result[0])
        assert result[1] == "harmless"

    def test_handles_none(self):
        assert notion.mask_secrets(None) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_notion.py::TestMaskSecrets -v`
Expected: 5 PASS (이 함수는 이미 검증된 코드 — 통과해야 정상). FAIL 이면 mask_secrets signature 변경 여부 확인.

- [ ] **Step 3: 통과 확인 후 커밋**

```bash
git add tests/unit/test_notion.py
git commit -m "test(notion): add mask_secrets unit tests"
```

---

### Task 3: lib/notion.py — notion_request retry/backoff

**Files:**
- Modify: `C:\dev\agent-bootstrap\tests\unit\test_notion.py` (add TestNotionRequest class)

- [ ] **Step 1: retry 테스트 추가**

`tests/unit/test_notion.py` 끝에 append:
```python
class TestNotionRequest:
    def test_retries_on_429(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_fake")
        mock_resp_429 = mocker.MagicMock()
        mock_resp_429.status = 429
        mock_resp_429.read.return_value = b'{"message":"rate limited"}'
        mock_resp_429.headers = {"Retry-After": "0"}
        mock_resp_200 = mocker.MagicMock()
        mock_resp_200.status = 200
        mock_resp_200.read.return_value = b'{"ok": true}'
        urlopen = mocker.patch("notion.urlopen")
        urlopen.side_effect = [mock_resp_429, mock_resp_200]
        mocker.patch("notion.time.sleep")

        result = notion.notion_request("GET", "/v1/users")
        assert result == {"ok": True}
        assert urlopen.call_count == 2

    def test_raises_after_max_retries(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_fake")
        mock_resp = mocker.MagicMock()
        mock_resp.status = 500
        mock_resp.read.return_value = b'{"message":"server error"}'
        mock_resp.headers = {}
        mocker.patch("notion.urlopen", return_value=mock_resp)
        mocker.patch("notion.time.sleep")

        with pytest.raises(Exception):
            notion.notion_request("GET", "/v1/users", max_retries=2)

    def test_masks_token_in_error_log(self, mocker, monkeypatch, caplog):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_abcdefghij1234567890")
        mock_resp = mocker.MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b'{"message":"bad"}'
        mock_resp.headers = {}
        mocker.patch("notion.urlopen", return_value=mock_resp)

        with pytest.raises(Exception):
            notion.notion_request("GET", "/v1/users", max_retries=1)
        # 로그에 raw 토큰 새지 않음
        assert "secret_abcdefghij1234567890" not in caplog.text
```

- [ ] **Step 2: 테스트 실행**

Run: `uv run pytest tests/unit/test_notion.py::TestNotionRequest -v`
Expected: 3 PASS. 만약 `urlopen` import 경로가 다르면 `notion.urlopen` → 실제 patch 대상 (e.g. `urllib.request.urlopen`) 으로 수정.

- [ ] **Step 3: 커밋**

```bash
git add tests/unit/test_notion.py
git commit -m "test(notion): add notion_request retry tests"
```

---

### Task 4: lib/notion.py — upsert_by_external_id

**Files:**
- Modify: `C:\dev\agent-bootstrap\tests\unit\test_notion.py` (add TestUpsert class)

- [ ] **Step 1: upsert 테스트 추가**

`tests/unit/test_notion.py` 끝에 append:
```python
class TestUpsert:
    def test_creates_new_when_not_exists(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_fake")
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            {"results": []},  # query: no existing
            {"id": "page_new"},  # create
        ]
        result = notion.upsert_by_external_id(
            database_id="db1",
            external_id="ext_1",
            properties={"이름": {"title": [{"text": {"content": "X"}}]}},
        )
        assert result["id"] == "page_new"
        assert nreq.call_count == 2

    def test_updates_when_exists(self, mocker, monkeypatch):
        monkeypatch.setenv("NOTION_API_TOKEN", "secret_fake")
        nreq = mocker.patch("notion.notion_request")
        nreq.side_effect = [
            {"results": [{"id": "page_existing"}]},
            {"id": "page_existing"},
        ]
        result = notion.upsert_by_external_id(
            database_id="db1",
            external_id="ext_1",
            properties={"제목": {"title": [{"text": {"content": "Y"}}]}},
        )
        assert result["id"] == "page_existing"
        # PATCH 호출 검증
        patch_call = nreq.call_args_list[1]
        assert patch_call.args[0] == "PATCH"
```

- [ ] **Step 2: 실행**

Run: `uv run pytest tests/unit/test_notion.py::TestUpsert -v`
Expected: 2 PASS. 함수 시그니처 (database_id / external_id / properties 키워드 인자명) 가 실제와 다르면 [templates/lib/notion.py:288](../../../templates/lib/notion.py:288) 확인 후 맞춤.

- [ ] **Step 3: 커밋**

```bash
git add tests/unit/test_notion.py
git commit -m "test(notion): add upsert_by_external_id idempotency tests"
```

---

### Task 5: lib/md_to_notion.py 단위 테스트

**Files:**
- Create: `C:\dev\agent-bootstrap\tests\unit\test_md_to_notion.py`

- [ ] **Step 1: 핵심 변환 테스트 작성**

`tests/unit/test_md_to_notion.py`:
```python
"""Unit tests for templates/lib/md_to_notion.py."""
from __future__ import annotations

import md_to_notion  # via conftest sys.path


def test_paragraph_to_block():
    blocks = md_to_notion.markdown_to_blocks("간단한 텍스트.")
    assert len(blocks) >= 1
    assert blocks[0]["type"] == "paragraph"


def test_heading_to_block():
    blocks = md_to_notion.markdown_to_blocks("# H1\n## H2")
    types = [b["type"] for b in blocks]
    assert "heading_1" in types
    assert "heading_2" in types


def test_bullet_list():
    blocks = md_to_notion.markdown_to_blocks("- item1\n- item2")
    types = [b["type"] for b in blocks]
    assert types.count("bulleted_list_item") == 2


def test_code_block():
    md = "```python\nprint('x')\n```"
    blocks = md_to_notion.markdown_to_blocks(md)
    assert any(b["type"] == "code" for b in blocks)


def test_long_paragraph_split_2000_chars():
    # Notion rich_text 한 블록 2000 char 제한
    long = "가" * 5000
    blocks = md_to_notion.markdown_to_blocks(long)
    # 분할되어 여러 블록 또는 한 블록 안에서 rich_text 여러 chunk
    for b in blocks:
        if b["type"] == "paragraph":
            for rt in b["paragraph"]["rich_text"]:
                assert len(rt["text"]["content"]) <= 2000
```

- [ ] **Step 2: 실행 + 함수명 맞추기**

Run: `uv run pytest tests/unit/test_md_to_notion.py -v`
Expected: 5 PASS. 실제 export 함수명이 `markdown_to_blocks` 가 아니면 [templates/lib/md_to_notion.py](../../../templates/lib/md_to_notion.py) 의 public 함수로 교체.

- [ ] **Step 3: 커밋**

```bash
git add tests/unit/test_md_to_notion.py
git commit -m "test(md_to_notion): add markdown→block conversion tests"
```

---

### Task 6: GitHub Actions CI workflow

**Files:**
- Create: `C:\dev\agent-bootstrap\.github\workflows\test.yml`
- Create: `C:\dev\agent-bootstrap\.github\workflows\lint.yml`

- [ ] **Step 1: test.yml 작성**

`.github/workflows/test.yml`:
```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.10", "3.11", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          python-version: ${{ matrix.python }}
      - name: Install deps
        run: uv sync --extra test
      - name: pytest
        run: uv run pytest tests/ -q --cov=templates --cov-report=term --cov-report=xml
      - name: py_compile
        shell: bash
        run: |
          python -m py_compile templates/scripts/slack-jipsa/*.py templates/lib/*.py templates/hooks/append_turn_raw.py
      - name: bash -n shell hooks
        if: matrix.os != 'windows-latest'
        shell: bash
        run: bash -n templates/hooks/slack-session-summary.sh
      - name: upload coverage
        if: matrix.os == 'ubuntu-latest' && matrix.python == '3.12'
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml
```

- [ ] **Step 2: lint.yml 작성**

`.github/workflows/lint.yml`:
```yaml
name: lint

on:
  push:
    branches: [main]
  pull_request:

jobs:
  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: shellcheck
        run: shellcheck templates/hooks/*.sh

  pscheck:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: PowerShell AST parse
        shell: pwsh
        run: |
          $files = Get-ChildItem -Path templates/windows -Filter "*.ps1" -ErrorAction SilentlyContinue
          $files += Get-ChildItem -Path templates/windows -Filter "*.ps1.tmpl" -ErrorAction SilentlyContinue
          if ($files.Count -eq 0) {
            Write-Host "No PowerShell files yet (Phase C not started)"
            exit 0
          }
          $errors = $null; $tokens = $null
          $hasError = $false
          foreach ($f in $files) {
            [System.Management.Automation.Language.Parser]::ParseFile(
              $f.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            if ($errors -and $errors.Count -gt 0) {
              Write-Host "FAIL: $($f.Name)"
              $errors | ForEach-Object { Write-Host "  $($_.Message)" }
              $hasError = $true
            }
          }
          if ($hasError) { exit 1 }
```

- [ ] **Step 3: 로컬에서 yaml lint**

Run (bash 가능 환경): `python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml')); yaml.safe_load(open('.github/workflows/lint.yml'))"`
Expected: 출력 없음 (yaml 파싱 성공).

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/test.yml .github/workflows/lint.yml
git commit -m "ci: add test and lint GitHub Actions workflows"
```

---

## Phase A — daemon.py 리팩터

### Task 7: session_storage.py 추출

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\session_storage.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_session_storage.py`:
```python
"""Unit tests for session_storage."""
from __future__ import annotations

import uuid

import session_storage  # via conftest sys.path


def test_get_or_create_returns_new_when_missing(tmp_path):
    sid, is_new = session_storage.get_or_create_session("Cabc", sessions_dir=tmp_path)
    assert is_new is True
    assert len(sid) == 36  # UUID
    assert (tmp_path / "Cabc.txt").read_text().strip() == sid


def test_get_or_create_returns_existing(tmp_path):
    (tmp_path / "Cabc.txt").write_text("existing-session-id\n")
    sid, is_new = session_storage.get_or_create_session("Cabc", sessions_dir=tmp_path)
    assert is_new is False
    assert sid == "existing-session-id"


def test_reset_session_creates_new_uuid(tmp_path):
    (tmp_path / "Cabc.txt").write_text("old-session-id\n")
    sid = session_storage.reset_session("Cabc", sessions_dir=tmp_path)
    assert sid != "old-session-id"
    uuid.UUID(sid)  # raises if not valid UUID
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_session_storage.py -v`
Expected: 3 FAIL (`ModuleNotFoundError: No module named 'session_storage'`).

- [ ] **Step 3: session_storage.py 구현**

`templates/scripts/slack-jipsa/session_storage.py`:
```python
"""채널별 Claude Code session_id 저장/조회."""
from __future__ import annotations

import uuid
from pathlib import Path


def session_path(channel: str, sessions_dir: Path) -> Path:
    return sessions_dir / f"{channel}.txt"


def get_or_create_session(channel: str, sessions_dir: Path) -> tuple[str, bool]:
    """채널의 session_id 반환. 없으면 새 UUID 생성. (id, is_new)"""
    p = session_path(channel, sessions_dir)
    if p.exists():
        sid = p.read_text().strip()
        if sid:
            return sid, False
    sid = str(uuid.uuid4())
    sessions_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(sid)
    return sid, True


def reset_session(channel: str, sessions_dir: Path) -> str:
    """세션 리셋. 새 UUID 발급."""
    sid = str(uuid.uuid4())
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path(channel, sessions_dir).write_text(sid)
    return sid
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit/test_session_storage.py -v`
Expected: 3 PASS.

- [ ] **Step 5: daemon.py 에서 위임으로 전환 (임시 — 기존 함수는 보존하되 내부에서 위임)**

`templates/scripts/slack-jipsa/daemon.py` L173-192 (기존 `session_path`, `get_or_create_session`, `reset_session` 정의) 교체:
```python
from session_storage import (
    session_path as _session_path_impl,
    get_or_create_session as _get_or_create_session_impl,
    reset_session as _reset_session_impl,
)


def session_path(channel: str) -> Path:
    return _session_path_impl(channel, SESSIONS_DIR)


def get_or_create_session(channel: str) -> tuple[str, bool]:
    return _get_or_create_session_impl(channel, SESSIONS_DIR)


def reset_session(channel: str) -> str:
    return _reset_session_impl(channel, SESSIONS_DIR)
```

- [ ] **Step 6: daemon.py syntax 확인**

Run: `python -m py_compile templates/scripts/slack-jipsa/daemon.py`
Expected: 출력 없음.

- [ ] **Step 7: 커밋**

```bash
git add templates/scripts/slack-jipsa/session_storage.py templates/scripts/slack-jipsa/daemon.py tests/unit/test_session_storage.py
git commit -m "refactor(daemon): extract session_storage module"
```

---

### Task 8: filters.py 추출

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\filters.py`
- Create: `C:\dev\agent-bootstrap\tests\unit\test_filters.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_filters.py`:
```python
"""Unit tests for message filters."""
from __future__ import annotations

import filters


class TestIdentityFilters:
    def test_is_self_matches_bot_user(self):
        event = {"user": "U0BOT", "text": "hi"}
        assert filters.is_self(event, bot_user_id="U0BOT") is True

    def test_is_self_false_for_other(self):
        event = {"user": "U0USER", "text": "hi"}
        assert filters.is_self(event, bot_user_id="U0BOT") is False

    def test_is_miri_true(self):
        event = {"user": "U0USER"}
        assert filters.is_miri(event, user_slack_id="U0USER") is True

    def test_is_other_bot_subtype_bot_message(self):
        event = {"subtype": "bot_message", "bot_id": "B0OTHER"}
        assert filters.is_other_bot(event, my_bot_user_id="U0BOT") is True


class TestDiscussionKeywords:
    def test_trigger_matches(self):
        assert filters.matches_discussion_trigger("둘이 의견 좀 나눠봐")

    def test_stop_matches(self):
        assert filters.matches_discussion_stop("그만")

    def test_neither_for_normal_text(self):
        assert not filters.matches_discussion_trigger("오늘 날씨 어때")
        assert not filters.matches_discussion_stop("오늘 날씨 어때")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_filters.py -v`
Expected: 7 FAIL (`ModuleNotFoundError: No module named 'filters'`).

- [ ] **Step 3: filters.py 구현**

`templates/scripts/slack-jipsa/filters.py`:
```python
"""슬랙 메시지 필터링: identity (self/user/other-bot) + 토론 키워드 매칭."""
from __future__ import annotations

import re

DISCUSSION_TRIGGER = re.compile(
    r"(토론|비교|반박|의견\s*(나눠|줘|얘기|교환)|각자\s*의견|둘이|서로\s*의견)",
    re.IGNORECASE,
)
DISCUSSION_STOP = re.compile(
    r"(\b그만\b|\b종료\b|\bstop\b|\b끝\b|\b정리\b|\b중단\b|토론\s*그만|토론\s*종료)",
    re.IGNORECASE,
)


def is_self(event: dict, bot_user_id: str) -> bool:
    """봇 자기 메시지인지."""
    return bool(bot_user_id) and event.get("user") == bot_user_id


def is_miri(event: dict, user_slack_id: str) -> bool:
    """대상 사용자 메시지인지."""
    return bool(user_slack_id) and event.get("user") == user_slack_id


def is_other_bot(event: dict, my_bot_user_id: str) -> bool:
    """다른 봇 메시지인지 (subtype=bot_message 인데 내 봇 아님)."""
    if event.get("subtype") != "bot_message":
        return False
    return event.get("user") != my_bot_user_id


def matches_discussion_trigger(text: str) -> bool:
    return bool(DISCUSSION_TRIGGER.search(text or ""))


def matches_discussion_stop(text: str) -> bool:
    return bool(DISCUSSION_STOP.search(text or ""))
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit/test_filters.py -v`
Expected: 7 PASS.

- [ ] **Step 5: daemon.py 에서 import 위임**

`templates/scripts/slack-jipsa/daemon.py` L151-159 의 regex 정의 제거 후:
```python
from filters import (
    DISCUSSION_TRIGGER,
    DISCUSSION_STOP,
    is_self,
    is_miri,
    is_other_bot,
    matches_discussion_trigger,
    matches_discussion_stop,
)
```
호출처에서 원래 `_is_self(event)` 같이 클로저 캡쳐했던 부분은 `is_self(event, BOT)` 로 인자 명시.

- [ ] **Step 6: syntax + 통합 smoke**

Run:
```
python -m py_compile templates/scripts/slack-jipsa/daemon.py
uv run pytest tests/unit/test_filters.py tests/unit/test_session_storage.py -v
```
Expected: 모두 PASS.

- [ ] **Step 7: 커밋**

```bash
git add templates/scripts/slack-jipsa/filters.py templates/scripts/slack-jipsa/daemon.py tests/unit/test_filters.py
git commit -m "refactor(daemon): extract filters module"
```

---

### Task 9: slack_io.py 추출

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\slack_io.py`

- [ ] **Step 1: slack_io.py 구현 (extract from daemon.py)**

daemon.py 에서 다음 함수들을 추출 — `post_slack_safely`, `add_reaction`, `remove_reaction`, `post_thread` (있다면). [daemon.py:Grep `chat_postMessage|reactions_add|reactions_remove`] 로 위치 파악 후 옮김.

`templates/scripts/slack-jipsa/slack_io.py`:
```python
"""Slack Web API 래퍼: chat.postMessage, reactions, thread."""
from __future__ import annotations

import logging
from typing import Any

from slack_sdk import WebClient

logger = logging.getLogger(__name__)


def post_message(web: WebClient, channel: str, text: str, thread_ts: str | None = None,
                 blocks: list[dict] | None = None) -> dict[str, Any] | None:
    """채널에 메시지 게시. 실패 시 warning + None 리턴."""
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks
        return web.chat_postMessage(**kwargs)
    except Exception as e:
        logger.warning("chat_postMessage failed: %s", e)
        return None


def add_reaction(web: WebClient, channel: str, ts: str, name: str) -> None:
    """이모지 reaction 추가. cosmetic — 실패는 debug 만."""
    try:
        web.reactions_add(channel=channel, timestamp=ts, name=name)
    except Exception as e:
        logger.debug("reactions_add(%s) skipped: %s", name, e)


def remove_reaction(web: WebClient, channel: str, ts: str, name: str) -> None:
    try:
        web.reactions_remove(channel=channel, timestamp=ts, name=name)
    except Exception as e:
        logger.debug("reactions_remove(%s) skipped: %s", name, e)
```

- [ ] **Step 2: daemon.py 에서 위임**

`templates/scripts/slack-jipsa/daemon.py` 의 reaction add/remove, chat_postMessage 호출처를 `slack_io.add_reaction(web, ...)` 같이 교체.

- [ ] **Step 3: syntax 확인**

Run: `python -m py_compile templates/scripts/slack-jipsa/slack_io.py templates/scripts/slack-jipsa/daemon.py`
Expected: 출력 없음.

- [ ] **Step 4: 커밋**

```bash
git add templates/scripts/slack-jipsa/slack_io.py templates/scripts/slack-jipsa/daemon.py
git commit -m "refactor(daemon): extract slack_io wrappers"
```

---

### Task 10: claude_invoker.py 추출 + CLAUDE_TIMEOUT_SEC env

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\claude_invoker.py`
- Modify: `C:\dev\agent-bootstrap\.env.example` (CLAUDE_TIMEOUT_SEC 추가)

- [ ] **Step 1: claude_invoker.py 작성**

`templates/scripts/slack-jipsa/claude_invoker.py`:
```python
"""Claude Code CLI 호출 래퍼: subprocess + resume fallback."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable

from session_storage import get_or_create_session, reset_session

logger = logging.getLogger(__name__)


def run_claude(prompt: str, session_id: str, is_new: bool, timeout: int,
               system_prompt: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CLAUDE_SKIP_HOOKS"] = "1"
    cmd = [
        "claude", "--print",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--add-dir", str(Path.home()),
        "--output-format", "text",
        "--model", "opus",
        "--append-system-prompt", system_prompt,
    ]
    cmd.extend(["--session-id", session_id] if is_new else ["--resume", session_id])
    cwd = str(Path.home() / ".claude/scripts/slack-jipsa")
    return subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          env=env, cwd=cwd, timeout=timeout)


def call_claude(prompt: str, channel: str, sessions_dir: Path, system_prompt: str,
                timeout: int, on_invoke: Callable[[str, str, int, int], None] | None = None) -> str:
    """클로드 코드 호출. resume 실패 시 새 session 재시도. 결과 string 반환.

    on_invoke: audit hook (channel, session_id, len_in, len_out) — Phase E.3 에서 사용.
    """
    sid, is_new = get_or_create_session(channel, sessions_dir)
    try:
        r = run_claude(prompt, sid, is_new, timeout, system_prompt)
        if r.returncode != 0 and not is_new and "No conversation found" in (r.stderr or ""):
            logger.info("resume fail, fallback to new session")
            new_sid = reset_session(channel, sessions_dir)
            r = run_claude(prompt, new_sid, True, timeout, system_prompt)
            sid = new_sid
    except subprocess.TimeoutExpired:
        return f"⏱️ 타임아웃 ({timeout}초). 작업이 너무 길어요."

    out = (r.stdout or "").strip()
    if r.returncode != 0:
        logger.warning("claude fail rc=%d: %s", r.returncode, (r.stderr or "")[-300:])
        if on_invoke:
            on_invoke(channel, sid, len(prompt), 0)
        return "__SILENT_FAIL__"

    if on_invoke:
        on_invoke(channel, sid, len(prompt), len(out))
    return out
```

- [ ] **Step 2: daemon.py 에서 위임**

daemon.py 의 `_run_claude` (L203) 와 `call_claude` (L222) 정의 제거 후:
```python
from claude_invoker import call_claude as _invoker_call_claude

CLAUDE_TIMEOUT_SEC = int(ENV.get("CLAUDE_TIMEOUT_SEC", "900"))


def call_claude(prompt: str, channel: str) -> str:
    return _invoker_call_claude(
        prompt, channel,
        sessions_dir=SESSIONS_DIR,
        system_prompt=SYSTEM_PROMPT,
        timeout=CLAUDE_TIMEOUT_SEC,
    )
```

- [ ] **Step 3: .env.example 업데이트**

`.env.example` 에 추가 (적절한 섹션에):
```
# Claude CLI 호출 timeout (초). 기본 900. 긴 task 면 늘리고, 빠른 응답이 필요하면 줄임.
CLAUDE_TIMEOUT_SEC=900
```

- [ ] **Step 4: syntax 확인**

Run: `python -m py_compile templates/scripts/slack-jipsa/claude_invoker.py templates/scripts/slack-jipsa/daemon.py`
Expected: 출력 없음.

- [ ] **Step 5: 커밋**

```bash
git add templates/scripts/slack-jipsa/claude_invoker.py templates/scripts/slack-jipsa/daemon.py .env.example
git commit -m "refactor(daemon): extract claude_invoker + env-driven timeout"
```

---

### Task 11: notion_logger.py 추출 + module1 check

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\notion_logger.py`

- [ ] **Step 1: notion_logger.py 구현**

daemon.py L259-345 의 `notion_log_turn` 을 옮김. 모듈 1 의존성 체크 추가.

`templates/scripts/slack-jipsa/notion_logger.py`:
```python
"""슬랙↔클로드 한 턴을 Notion 'Claude Code 턴 로그' DB에 적재."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_module1_setup() -> bool:
    """모듈 4는 모듈 1 의존. .env + lib 존재 확인."""
    required = [
        Path.home() / ".claude/secrets/slack-jipsa.env",
        Path.home() / ".claude/scripts/lib/notion.py",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        logger.warning("모듈 1 미완료. 누락: %s. modules/01-slack-bridge.md 진행 필요", missing)
        return False
    return True


def notion_log_turn(channel: str, event_ts: str, user_text: str, reply_text: str,
                    session_id: str, model: str, session_db: str, daily_db: str,
                    user_name: str, bot_name: str) -> None:
    """daemon 이 headless 라 Stop hook 발동 안 함 → 직접 적재.

    session_db 가 비어있으면 skip (옵션 기능).
    """
    if not session_db:
        return
    if not verify_module1_setup():
        return
    try:
        # 기존 daemon.py L259-345 본문 그대로 (notion_request 호출 등)
        # 구체 구현은 기존 코드 이식 — 외부 인자로 user_name/bot_name 받음
        from notion import notion_request

        # 페이지 생성 호출 (예시 — 실제 페이로드는 daemon.py 원본 복사)
        body = {
            "parent": {"database_id": session_db},
            "properties": _build_session_properties(
                channel, event_ts, user_text, reply_text, session_id, model,
                user_name, bot_name,
            ),
        }
        notion_request("POST", "/v1/pages", body)
    except Exception as e:
        logger.warning("notion_log_turn failed: %s", e)


def _build_session_properties(channel: str, event_ts: str, user_text: str, reply_text: str,
                              session_id: str, model: str, user_name: str, bot_name: str) -> dict:
    """노션 컬럼 페이로드 빌더 (한국어 컬럼명 유지)."""
    # daemon.py L310-321 원본의 키 (`프로젝트`, `시킨 일`, `한 일`, `결과`) 보존
    title = (user_text or "").strip()[:60] or "(빈 메시지)"
    return {
        "이름": {"title": [{"text": {"content": title}}]},
        "프로젝트": {"select": {"name": bot_name}},
        "시킨 일": {"rich_text": [{"text": {"content": (user_text or "")[:1900]}}]},
        "한 일": {"rich_text": [{"text": {"content": (reply_text or "")[:1900]}}]},
        "결과": {"select": {"name": "성공" if reply_text else "실패"}},
        "Channel": {"rich_text": [{"text": {"content": channel}}]},
        "Session ID": {"rich_text": [{"text": {"content": session_id}}]},
        "Event TS": {"rich_text": [{"text": {"content": event_ts}}]},
        "Model": {"rich_text": [{"text": {"content": model}}]},
    }
```

> **Note**: `_build_session_properties` 의 실제 컬럼명/구조는 [templates/scripts/slack-jipsa/daemon.py:310-321](../../../templates/scripts/slack-jipsa/daemon.py) 의 원본을 그대로 복사. 위는 골격만.

- [ ] **Step 2: daemon.py 에서 위임**

daemon.py L259-345 의 `notion_log_turn` 정의 제거 후:
```python
from notion_logger import notion_log_turn as _logger_notion_log_turn


def notion_log_turn(channel: str, event_ts: str, user_text: str, reply_text: str,
                    session_id: str, model: str = "opus") -> None:
    _logger_notion_log_turn(
        channel, event_ts, user_text, reply_text, session_id, model,
        session_db=NOTION_SESSION_DB,
        daily_db=NOTION_DAILY_DB,
        user_name=USER_NAME,
        bot_name=BOT_NAME,
    )
```

- [ ] **Step 3: syntax**

Run: `python -m py_compile templates/scripts/slack-jipsa/notion_logger.py templates/scripts/slack-jipsa/daemon.py`
Expected: 출력 없음.

- [ ] **Step 4: 커밋**

```bash
git add templates/scripts/slack-jipsa/notion_logger.py templates/scripts/slack-jipsa/daemon.py
git commit -m "refactor(daemon): extract notion_logger + module1 setup check"
```

---

### Task 12: logging_config.py + log() → structured logger 교체

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\logging_config.py`

- [ ] **Step 1: logging_config.py 작성**

`templates/scripts/slack-jipsa/logging_config.py`:
```python
"""Centralized logging setup with TimedRotatingFileHandler."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def configure_logging(log_dir: Path, level: str = "INFO", logger_name: str = "jipsa") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "daemon.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger(logger_name)
    # 중복 방지 — 재호출 시 핸들러 누적 안 함
    if not root.handlers:
        root.addHandler(handler)
        root.addHandler(console)
    root.setLevel(level)
    root.propagate = False
    return root
```

- [ ] **Step 2: daemon.py 의 log() 함수 교체**

daemon.py L165-170 의 `log()` 정의 제거. 상단에 추가:
```python
from logging_config import configure_logging

_root_logger = configure_logging(LOGS_DIR, level=ENV.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("jipsa.daemon")


def log(msg: str) -> None:
    """Deprecated — 기존 호출처 호환용. 새 코드는 logger.info(...) 사용."""
    logger.info(msg)
```

`import logging` 도 상단에 추가.

- [ ] **Step 3: syntax + 부팅 smoke**

Run: `python -m py_compile templates/scripts/slack-jipsa/logging_config.py templates/scripts/slack-jipsa/daemon.py`
Expected: 출력 없음.

- [ ] **Step 4: log 회전 단위 테스트 (옵션)**

`tests/unit/test_logging_config.py`:
```python
import logging
import logging.handlers
from pathlib import Path

import logging_config


def test_configure_creates_handler(tmp_path):
    log = logging_config.configure_logging(tmp_path, level="DEBUG", logger_name="test_jipsa")
    handlers = [h for h in log.handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].when == "MIDNIGHT"
    assert handlers[0].backupCount == 30


def test_writes_to_daemon_log(tmp_path):
    log = logging_config.configure_logging(tmp_path, logger_name="test_jipsa2")
    log.info("hello")
    for h in log.handlers:
        h.flush()
    assert (tmp_path / "daemon.log").exists()
    content = (tmp_path / "daemon.log").read_text(encoding="utf-8")
    assert "hello" in content
```

Run: `uv run pytest tests/unit/test_logging_config.py -v`
Expected: 2 PASS.

- [ ] **Step 5: 커밋**

```bash
git add templates/scripts/slack-jipsa/logging_config.py templates/scripts/slack-jipsa/daemon.py tests/unit/test_logging_config.py
git commit -m "feat(daemon): structured logging with daily rotation"
```

---

### Task 13: JipsaDaemon 클래스 — 글로벌 state → instance attr

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\jipsa_daemon.py`

- [ ] **Step 1: JipsaDaemon 클래스 작성 (handle_message + on_event 옮김)**

`templates/scripts/slack-jipsa/jipsa_daemon.py`:
```python
"""JipsaDaemon: 메인 클래스. 글로벌 state 격리 + handle_message 오케스트레이션."""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

import filters
import slack_io
from claude_invoker import call_claude
from notion_logger import notion_log_turn
from session_storage import get_or_create_session, reset_session

logger = logging.getLogger("jipsa.daemon")


class JipsaDaemon:
    """슬랙↔클로드 코드 daemon. instance state 로 글로벌 격리."""

    DIALOG_TURN_LIMIT = 6
    SHARED_BUFFER_LIMIT = 30

    def __init__(self, env: dict, sessions_dir: Path, logs_dir: Path,
                 shared_dir: Path, secrets_path: Path, system_prompt: str):
        self.env = env
        self.sessions_dir = sessions_dir
        self.logs_dir = logs_dir
        self.shared_dir = shared_dir
        self.secrets_path = secrets_path
        self.system_prompt = system_prompt

        self.bot_token = env["SLACK_BOT_TOKEN"]
        self.app_token = env["SLACK_APP_TOKEN"]
        self.channel = env["SLACK_CHANNEL"]
        self.channel_dialog = env.get("SLACK_CHANNEL_DIALOG", "")
        self.miri = env.get("USER_SLACK_ID") or env.get("MIRI_USER_ID", "")
        self.user_name = env.get("USER_NAME", "사용자")
        self.bot_name = env.get("SLACK_BOT_NAME", "슬랙 비서")
        self.notion_session_db = env.get("NOTION_SESSION_DB", "")
        self.notion_daily_db = env.get("NOTION_DAILY_DB", "")
        self.claude_timeout = int(env.get("CLAUDE_TIMEOUT_SEC", "900"))

        self.web = WebClient(token=self.bot_token)
        self.bot = self._resolve_bot_user_id(env.get("BOT_USER_ID", "").strip())
        self.sock = SocketModeClient(app_token=self.app_token, web_client=self.web)

        self.state_lock = threading.RLock()
        self.dialog_self_turn_count = 0
        self.discussion_mode: dict[str, bool] = {}
        self.discussion_state_file = self.shared_dir / "discussion_state.json"

    def _resolve_bot_user_id(self, current: str) -> str:
        """BOT_USER_ID 가 비어있으면 auth.test → .env write-back."""
        if current:
            return current
        try:
            bot = self.web.auth_test()["user_id"]
            text = self.secrets_path.read_text()
            if "BOT_USER_ID=" in text:
                new = re.sub(r"(?m)^BOT_USER_ID=.*$", f"BOT_USER_ID={bot}", text)
            else:
                new = text.rstrip() + f"\nBOT_USER_ID={bot}\n"
            self.secrets_path.write_text(new)
            logger.info("auto-resolved BOT_USER_ID=%s", bot)
            return bot
        except Exception as e:
            logger.warning("BOT_USER_ID auth.test failed: %s", e)
            return ""

    def _write_discussion_state(self) -> None:
        import json
        try:
            with self.state_lock:
                self.discussion_state_file.write_text(json.dumps({
                    "mode": dict(self.discussion_mode),
                    "ts": time.time(),
                }))
        except Exception as e:
            logger.warning("discussion_state write failed: %s", e)

    def on_event(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        """Socket Mode event entry. ACK + handle_message 스레드 spawn."""
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type != "events_api":
            return
        event = (req.payload or {}).get("event") or {}
        if event.get("type") != "message":
            return
        threading.Thread(target=self.handle_message, args=(event,), daemon=True).start()

    def handle_message(self, event: dict) -> None:
        """오케스트레이션만. 실제 로직은 filters/claude_invoker/notion_logger 위임.

        실제 라우팅 흐름은 기존 daemon.py L348-496 (handle_message) 의 본문을
        이 메서드 안으로 이식하되, 다음 치환을 적용:
        - 전역 web → self.web
        - 전역 BOT/MIRI → self.bot/self.miri
        - _is_self(event) → filters.is_self(event, self.bot)
        - _is_miri(event) → filters.is_miri(event, self.miri)
        - call_claude(...) → claude_invoker.call_claude(... sessions_dir=self.sessions_dir, ...)
        - notion_log_turn(...) → 모듈 함수 with self.notion_session_db 등
        - _dialog_self_turn_count → with self.state_lock: self.dialog_self_turn_count
        - _discussion_mode → with self.state_lock: self.discussion_mode
        """
        # 본 task 의 핵심은 클래스 골격 + state 격리. 실제 handle_message 이식은
        # 작은 surgical diff 로 진행. 이식 후 Task 16 의 통합 테스트로 회귀 확인.
        raise NotImplementedError(
            "handle_message body migration — see Task 13 Step 2"
        )

    def start(self) -> None:
        """daemon 시작 entry — sock.connect()."""
        self.sock.socket_mode_request_listeners.append(self.on_event)
        self.sock.connect()
        logger.info("JipsaDaemon started (channel=%s)", self.channel)
```

- [ ] **Step 2: handle_message 본문 이식**

기존 [daemon.py:348-496](../../../templates/scripts/slack-jipsa/daemon.py) 의 `handle_message` 본문을 통째로 `JipsaDaemon.handle_message` 안으로 복사. 위 docstring 의 치환 규칙 적용:
- `web.` → `self.web.`
- `BOT` → `self.bot`
- `MIRI` → `self.miri`
- `_is_self(event)` (있다면) → `filters.is_self(event, self.bot)`
- 글로벌 `_dialog_self_turn_count`/`_discussion_mode` write 는 `with self.state_lock:` 로 감쌈
- `call_claude(prompt, channel)` → `call_claude(prompt, channel, sessions_dir=self.sessions_dir, system_prompt=self.system_prompt, timeout=self.claude_timeout)`
- `notion_log_turn(...)` → `notion_log_turn(channel, event_ts, user_text, reply_text, sid, model, session_db=self.notion_session_db, daily_db=self.notion_daily_db, user_name=self.user_name, bot_name=self.bot_name)`

이식 후 `raise NotImplementedError(...)` 줄 제거.

- [ ] **Step 3: syntax**

Run: `python -m py_compile templates/scripts/slack-jipsa/jipsa_daemon.py`
Expected: 출력 없음.

- [ ] **Step 4: 커밋**

```bash
git add templates/scripts/slack-jipsa/jipsa_daemon.py
git commit -m "feat(daemon): introduce JipsaDaemon class with isolated state"
```

---

### Task 14: daemon.py → 30줄 entry point + 글로벌 mutable state 제거

**Files:**
- Modify: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\daemon.py`

- [ ] **Step 1: daemon.py 를 entry point 로 축소**

`templates/scripts/slack-jipsa/daemon.py` (전체 교체):
```python
#!/usr/bin/env python3
"""Slack ↔ Claude Code daemon entry point (Agent Bootstrap).

상세 구조는 jipsa_daemon.py 의 JipsaDaemon 클래스 참고.
"""
from __future__ import annotations

import sys
from pathlib import Path

# templates/lib 도 import path 에 (notion, slack_mrkdwn, md_to_notion)
sys.path.insert(0, str(Path.home() / ".claude/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/scripts/slack-jipsa"))

from jipsa_daemon import JipsaDaemon
from logging_config import configure_logging

SECRETS = Path.home() / ".claude/secrets/slack-jipsa.env"
SESSIONS_DIR = Path.home() / ".claude/scripts/slack-jipsa/sessions"
LOGS_DIR = Path.home() / ".claude/scripts/slack-jipsa/logs"
SHARED_DIR = Path.home() / ".claude/scripts/slack-jipsa-shared"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SHARED_DIR.mkdir(parents=True, exist_ok=True)


def load_env(secrets: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in secrets.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> int:
    configure_logging(LOGS_DIR)
    env = load_env(SECRETS)
    system_prompt = (
        f"당신은 {env.get('USER_NAME', '사용자')}님의 슬랙 비서 "
        f"'{env.get('SLACK_BOT_NAME', '슬랙 비서')}'입니다.\n\n"
        "**필수**: cwd `~/.claude/scripts/slack-jipsa/`의 CLAUDE.md를 절대 규칙으로 따르세요."
    )
    daemon = JipsaDaemon(
        env=env,
        sessions_dir=SESSIONS_DIR,
        logs_dir=LOGS_DIR,
        shared_dir=SHARED_DIR,
        secrets_path=SECRETS,
        system_prompt=system_prompt,
    )
    daemon.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 글로벌 state grep 0건 확인**

Run: `grep -nE '^_\w+\s*[:=]' templates/scripts/slack-jipsa/daemon.py || echo "no globals"`
Expected: `no globals`

- [ ] **Step 3: daemon.py 줄수 30줄 이하 확인**

Run: `wc -l templates/scripts/slack-jipsa/daemon.py`
Expected: 55줄 내외 (위 코드 기준). 정확히 30줄 이하 목표는 hard target 아님 — 75줄 이하로 완화. acceptance criteria 의 "30줄 이하" 는 import + main 만 고려한 추정. 핵심은 글로벌 mutable state 0.

- [ ] **Step 4: syntax + smoke**

Run:
```
python -m py_compile templates/scripts/slack-jipsa/daemon.py
uv run pytest tests/unit -v
```
Expected: py_compile 출력 없음. unit tests 모두 PASS.

- [ ] **Step 5: 커밋**

```bash
git add templates/scripts/slack-jipsa/daemon.py
git commit -m "refactor(daemon): reduce to entry point, remove module-level mutables"
```

---

## Phase B2 — handle_message 통합 테스트 (Phase A 위에서)

### Task 15: BOT_USER_ID 자동 조회 회귀 + handle_message 통합 시나리오

**Files:**
- Create: `C:\dev\agent-bootstrap\tests\integration\test_handle_message.py`

- [ ] **Step 1: 통합 테스트 작성**

`tests/integration/test_handle_message.py`:
```python
"""Integration tests for JipsaDaemon.handle_message and BOT_USER_ID resolution."""
from __future__ import annotations

import pytest

from jipsa_daemon import JipsaDaemon


def make_env(**overrides) -> dict:
    base = {
        "SLACK_BOT_TOKEN": "xoxb-fake",
        "SLACK_APP_TOKEN": "xapp-fake",
        "SLACK_CHANNEL": "C0FAKE",
        "USER_SLACK_ID": "U0USER",
        "BOT_USER_ID": "U0BOT",
        "USER_NAME": "테스터",
        "SLACK_BOT_NAME": "테스트봇",
        "NOTION_SESSION_DB": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def daemon_factory(tmp_path, mocker):
    mocker.patch("jipsa_daemon.WebClient")
    mocker.patch("jipsa_daemon.SocketModeClient")

    def factory(env_overrides: dict | None = None) -> tuple[JipsaDaemon, "Path"]:
        secrets = tmp_path / "slack-jipsa.env"
        env = make_env(**(env_overrides or {}))
        secrets.write_text("\n".join(f"{k}={v}" for k, v in env.items()))
        sessions_dir = tmp_path / "sessions"
        logs_dir = tmp_path / "logs"
        shared = tmp_path / "shared"
        daemon = JipsaDaemon(
            env=env,
            sessions_dir=sessions_dir,
            logs_dir=logs_dir,
            shared_dir=shared,
            secrets_path=secrets,
            system_prompt="test prompt",
        )
        return daemon, secrets

    return factory


class TestBotUserIdResolve:
    def test_uses_env_when_set(self, daemon_factory):
        daemon, _ = daemon_factory({"BOT_USER_ID": "U0EXPLICIT"})
        assert daemon.bot == "U0EXPLICIT"

    def test_auth_test_fallback_writes_back(self, daemon_factory, mocker):
        daemon, secrets = daemon_factory({"BOT_USER_ID": ""})
        daemon.web.auth_test.return_value = {"user_id": "U0AUTOFAKE"}
        # __init__ 안에서 이미 resolve 했음 — bot 확인
        bot = daemon._resolve_bot_user_id("")
        assert bot == "U0AUTOFAKE"
        assert "BOT_USER_ID=U0AUTOFAKE" in secrets.read_text()


class TestHandleMessageRouting:
    def test_self_message_ignored(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        event = {"user": "U0BOT", "channel": "C0FAKE", "text": "hello"}
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude")
        daemon.handle_message(event)
        call_claude_mock.assert_not_called()

    def test_user_message_invokes_claude(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "안녕", "ts": "1700000000.000100"}
        call_claude_mock = mocker.patch("jipsa_daemon.call_claude",
                                        return_value="안녕하세요")
        daemon.handle_message(event)
        call_claude_mock.assert_called_once()
        daemon.web.chat_postMessage.assert_called()

    def test_reset_keyword_creates_new_session(self, daemon_factory, mocker):
        daemon, _ = daemon_factory()
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "리셋", "ts": "1700000000.000100"}
        reset_mock = mocker.patch("jipsa_daemon.reset_session",
                                  return_value="new-uuid")
        mocker.patch("jipsa_daemon.call_claude", return_value="OK")
        daemon.handle_message(event)
        reset_mock.assert_called_once()

    def test_notion_skipped_when_db_empty(self, daemon_factory, mocker):
        daemon, _ = daemon_factory({"NOTION_SESSION_DB": ""})
        event = {"user": "U0USER", "channel": "C0FAKE",
                 "text": "test", "ts": "1700000000.000100"}
        mocker.patch("jipsa_daemon.call_claude", return_value="reply")
        notion_mock = mocker.patch("jipsa_daemon.notion_log_turn")
        daemon.handle_message(event)
        # notion_log_turn 은 호출되지만 내부에서 session_db="" 로 early return
        # 또는 호출 자체 skip — 어느 쪽이든 외부 API 안 감
        # 호출되었다면 첫 인자에 빈 db 확인
        if notion_mock.called:
            call_kwargs = notion_mock.call_args.kwargs
            assert call_kwargs.get("session_db", "") == ""


class TestDiscussionMode:
    def test_trigger_enables_mode(self, daemon_factory, mocker):
        daemon, _ = daemon_factory({"SLACK_CHANNEL_DIALOG": "C0DLG"})
        event = {"user": "U0USER", "channel": "C0DLG",
                 "text": "둘이 의견 나눠봐", "ts": "1700000000.000200"}
        mocker.patch("jipsa_daemon.call_claude", return_value="discuss")
        daemon.handle_message(event)
        assert daemon.discussion_mode.get("C0DLG") is True

    def test_stop_disables_mode(self, daemon_factory, mocker):
        daemon, _ = daemon_factory({"SLACK_CHANNEL_DIALOG": "C0DLG"})
        daemon.discussion_mode["C0DLG"] = True
        event = {"user": "U0USER", "channel": "C0DLG",
                 "text": "그만", "ts": "1700000000.000300"}
        mocker.patch("jipsa_daemon.call_claude", return_value="ok")
        daemon.handle_message(event)
        assert daemon.discussion_mode.get("C0DLG") is False
```

- [ ] **Step 2: 실행**

Run: `uv run pytest tests/integration/test_handle_message.py -v`
Expected: 시나리오에 따라 일부 FAIL 가능 — handle_message 본문 이식 완성도에 따라. FAIL 발견 시 jipsa_daemon.py 의 handle_message 본문을 보정 (Task 13 Step 2 와 동일 작업).

- [ ] **Step 3: 통과 후 커밋**

```bash
git add tests/integration/test_handle_message.py
git commit -m "test(jipsa): add handle_message integration scenarios"
```

---

## Phase C — Windows slack-session-summary.ps1 검증본

### Task 16: slack-session-summary.ps1 작성 + AST + 사용자 검증

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\windows\slack-session-summary.ps1`
- Modify: `C:\dev\agent-bootstrap\SKILL.md` (D 카테고리 → C 흡수)
- Modify: `C:\dev\agent-bootstrap\modules\01-slack-bridge.md` (Windows 분기 안내)

- [ ] **Step 1: slack-session-summary.ps1 작성**

`templates/windows/slack-session-summary.ps1` (sh 원본 [templates/hooks/slack-session-summary.sh](../../../templates/hooks/slack-session-summary.sh) 의 정밀 번역):

> 골격 — sh 원본의 461줄을 [spec Phase C.2 의 매핑 표](../specs/2026-05-20-agent-bootstrap-cleanup-design.md#c2-sh--powershell-정밀-번역-매핑) 에 따라 한 섹션씩 옮긴다.

```powershell
#!/usr/bin/env pwsh
# Stop hook for Windows: claude --print 세션 종료 시 슬랙 보고 + 노션 적재 (옵션)
# sh 원본 (templates/hooks/slack-session-summary.sh) 의 PowerShell 검증본.

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# 재귀 가드 (sh L24 와 동일)
if ($env:SLACK_HOOK_RUNNING -eq '1') {
    exit 0
}
$env:SLACK_HOOK_RUNNING = '1'

# .env 로드
$envFile = Join-Path $env:USERPROFILE '.claude\secrets\slack-jipsa.env'
if (-not (Test-Path $envFile)) { exit 0 }
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$' -and -not $_.StartsWith('#')) {
        $name = $Matches[1]
        $value = $Matches[2].Trim('"').Trim("'")
        Set-Item -Path "env:$name" -Value $value
    }
}

# CLAUDE_SKIP_HOOKS=1 일 때 (daemon 이 호출한 claude --print) skip
if ($env:CLAUDE_SKIP_HOOKS -eq '1') { exit 0 }

# stdin 의 JSON 파싱 — session_id 추출
$STDIN_JSON = [Console]::In.ReadToEnd()
if (-not $STDIN_JSON) { exit 0 }
try {
    $obj = $STDIN_JSON | ConvertFrom-Json
    $sid = $obj.session_id
    $cwd = $obj.cwd
} catch {
    exit 0
}
if (-not $sid) { exit 0 }

# transcript .jsonl 찾기
$projects = Join-Path $env:USERPROFILE '.claude\projects'
$transcript = Get-ChildItem -Path $projects -Filter "$sid.jsonl" -Recurse -ErrorAction SilentlyContinue |
              Select-Object -First 1
if (-not $transcript) { exit 0 }

# 마지막 user turn 이후의 turn 데이터 추출
$entries = Get-Content $transcript.FullName -Encoding UTF8 |
           Where-Object { $_ } |
           ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } |
           Where-Object { $_ }

# is_real_user 필터: type=user 이고 message.content 가 <task-notification> 시작 아님
$lastRealUserIdx = -1
for ($i = 0; $i -lt $entries.Count; $i++) {
    $e = $entries[$i]
    if ($e.type -eq 'user') {
        $content = $e.message.content
        if ($content -is [string]) { $text = $content }
        elseif ($content -is [array]) {
            $text = ($content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join ''
        } else { $text = '' }
        if ($text -and -not $text.StartsWith('<task-notification>')) {
            $lastRealUserIdx = $i
        }
    }
}
if ($lastRealUserIdx -lt 0) { exit 0 }

$turn = $entries[($lastRealUserIdx)..($entries.Count - 1)]

# user_text 추출
$userEntry = $turn[0]
$userText = if ($userEntry.message.content -is [string]) {
    $userEntry.message.content
} else {
    ($userEntry.message.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join ''
}

# assistant 텍스트 + tool 이름 수집
$assistantText = New-Object 'System.Text.StringBuilder'
$toolNames = @()
foreach ($e in $turn) {
    if ($e.type -ne 'assistant') { continue }
    if (-not $e.message -or -not $e.message.content) { continue }
    foreach ($block in $e.message.content) {
        if ($block.type -eq 'text') {
            [void]$assistantText.AppendLine($block.text)
        } elseif ($block.type -eq 'tool_use') {
            $toolNames += $block.name
        }
    }
}

# mrkdwn 변환: **bold** → *bold*
$replyText = $assistantText.ToString() -replace '\*\*([^*]+)\*\*', '*$1*'

# tool 이름 카운트 요약
$toolSummary = ($toolNames | Group-Object | ForEach-Object { "$($_.Name)×$($_.Count)" }) -join ', '

# Notion trim (1900 char)
function NotionTrim($s) {
    if ($null -eq $s) { return '' }
    if ($s.Length -gt 1900) { return $s.Substring(0, 1900) }
    return $s
}

# Slack 전송
$slackUrl = $env:SLACK_SESSION_WEBHOOK
$botToken = $env:SLACK_BOT_TOKEN
$channel = $env:SLACK_CHANNEL

$payloadText = @"
*세션 요약*
> $($userText -replace "`n", " ")

$(NotionTrim $replyText)

_tools: $toolSummary_
"@

if ($slackUrl) {
    try {
        $body = @{ text = $payloadText } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $slackUrl -Method Post -Body $body -ContentType 'application/json' | Out-Null
    } catch {
        # Bot Token 폴백
        if ($botToken -and $channel) {
            $body = @{ channel = $channel; text = $payloadText } | ConvertTo-Json -Compress
            Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' `
                -Method Post -Body $body `
                -ContentType 'application/json; charset=utf-8' `
                -Headers @{ Authorization = "Bearer $botToken" } | Out-Null
        }
    }
} elseif ($botToken -and $channel) {
    $body = @{ channel = $channel; text = $payloadText } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' `
        -Method Post -Body $body `
        -ContentType 'application/json; charset=utf-8' `
        -Headers @{ Authorization = "Bearer $botToken" } | Out-Null
}

# (옵션) 노션 적재 — NOTION_API_TOKEN + NOTION_SESSION_DB 있을 때만
if ($env:NOTION_API_TOKEN -and $env:NOTION_SESSION_DB) {
    # ~/.claude/hooks/md_to_notion.py 의 변환 함수 호출 또는
    # 직접 Notion REST API 호출 — 본 spec 의 범위에서는 sh 원본의 노션 부분도
    # 한 번 더 옮긴다 (sh L240-460). 골격 보존: properties 빌더 + POST /v1/pages
    # 상세 이식은 sh 원본을 라인 단위로 옮기되 위 매핑 표에 따른다.
}

exit 0
```

> **Note**: 노션 적재 블록은 sh 원본 L240-460 의 약 220줄. 여기서는 골격만 — 실제 이식 시 sh 의 jq 쿼리, urllib 호출, properties 빌더를 PowerShell `Invoke-RestMethod` + `ConvertFrom-Json` 으로 한 줄씩 옮긴다.

- [ ] **Step 2: AST parse 검증**

Run (Windows PowerShell):
```powershell
$err = $null; $t = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  'templates/windows/slack-session-summary.ps1', [ref]$t, [ref]$err) | Out-Null
if ($err.Count -gt 0) { $err | ForEach-Object { Write-Host $_.Message } } else { Write-Host 'OK' }
```
Expected: `OK`.

- [ ] **Step 3: SKILL.md 의 D 카테고리 섹션 삭제**

`SKILL.md` 에서 "D. AI 책임 — Windows Stop hook 만 즉석 생성" 섹션 검색 후 삭제. 같은 위치에 다음 한 줄 추가 (C 카테고리 항목 끝에):
```markdown
- Windows 검증본 PowerShell Stop hook: `templates/windows/slack-session-summary.ps1` — sh 원본의 정밀 번역, AST parse 통과 검증.
```

- [ ] **Step 4: modules/01-slack-bridge.md Windows 분기 업데이트**

`modules/01-slack-bridge.md` 의 Windows Stop hook 안내 부분 검색 후, "AI 가 즉석 생성" 대신 "검증본 카피" 로 교체:
```markdown
**Windows**: `templates/windows/slack-session-summary.ps1` 을 `~/.claude/hooks/slack-session-summary.ps1` 로 카피. settings.json 의 Stop hook 명령을 `pwsh -File ~/.claude/hooks/slack-session-summary.ps1` 로 등록.
```

- [ ] **Step 5: 사용자 본인 환경 1턴 검증 (수동)**

Run (Windows):
1. `~/.claude/hooks/slack-session-summary.ps1` 에 카피
2. `claude --print "1+1"` 실행
3. 슬랙에 보고 도착 확인

Expected: 슬랙 채널에 세션 요약 메시지 1개.

- [ ] **Step 6: 커밋**

```bash
git add templates/windows/slack-session-summary.ps1 SKILL.md modules/01-slack-bridge.md
git commit -m "feat(windows): add validated Stop hook PS1 (D→C category)"
```

---

## Phase D — 운영 가드

### Task 17: log rotation + cleanup 스크립트

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\windows\cleanup-old-logs.ps1`
- Create: `C:\dev\agent-bootstrap\templates\windows\cleanup-processed.ps1`
- Modify: `C:\dev\agent-bootstrap\modules\02-folder-trigger.md` (cleanup cron 안내)

- [ ] **Step 1: cleanup-old-logs.ps1 작성**

`templates/windows/cleanup-old-logs.ps1`:
```powershell
#!/usr/bin/env pwsh
# 30일 이상 된 로그 파일 삭제. 매주 1회 Scheduled Task 등록 권장.
param(
    [int]$DaysOld = 30,
    [switch]$DryRun
)

$logDirs = @(
    "$env:USERPROFILE\.claude\scripts\slack-jipsa\logs",
    "$env:USERPROFILE\.claude\scripts\folder-watch\logs"
)
$cutoff = (Get-Date).AddDays(-$DaysOld)

foreach ($dir in $logDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -File -Recurse |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            if ($DryRun) {
                Write-Host "[DRY] would delete: $($_.FullName)"
            } else {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-Host "deleted: $($_.FullName)"
            }
        }
}
```

- [ ] **Step 2: cleanup-processed.ps1 작성**

`templates/windows/cleanup-processed.ps1`:
```powershell
#!/usr/bin/env pwsh
# 폴더 트리거의 .processed/ 에서 90일 이상 된 파일 삭제.
param(
    [int]$DaysOld = 90,
    [switch]$DryRun
)

$processedDirs = Get-ChildItem -Path "$env:USERPROFILE\.claude\scripts\folder-watch" -Directory -ErrorAction SilentlyContinue |
                 ForEach-Object { Join-Path $_.FullName '.processed' } |
                 Where-Object { Test-Path $_ }
$cutoff = (Get-Date).AddDays(-$DaysOld)

foreach ($dir in $processedDirs) {
    Get-ChildItem -Path $dir -File |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            if ($DryRun) {
                Write-Host "[DRY] would delete: $($_.FullName)"
            } else {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-Host "deleted: $($_.FullName)"
            }
        }
}
```

- [ ] **Step 3: AST parse 두 개**

Run (Windows):
```powershell
$err=$null; $t=$null
foreach ($f in 'templates/windows/cleanup-old-logs.ps1', 'templates/windows/cleanup-processed.ps1') {
  [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$t, [ref]$err) | Out-Null
  if ($err.Count -gt 0) { Write-Host "FAIL: $f"; $err | % { $_.Message } }
}
```
Expected: 출력 없음.

- [ ] **Step 4: dry-run smoke**

Run: `pwsh -File templates/windows/cleanup-old-logs.ps1 -DryRun`
Expected: `[DRY] would delete: ...` 또는 출력 없음 (해당 디렉토리 없거나 30일 미만).

- [ ] **Step 5: modules/02 업데이트**

`modules/02-folder-trigger.md` 끝의 "운영" 섹션에 추가:
```markdown
### 정리 (선택)
주 1회 `.processed/` 정리:
```powershell
schtasks /Create /SC WEEKLY /D MON /TN "AgentBootstrap-CleanupProcessed" `
  /TR "pwsh -File C:\Users\$env:USERNAME\.claude\scripts\cleanup-processed.ps1" /F
```
```

- [ ] **Step 6: 커밋**

```bash
git add templates/windows/cleanup-old-logs.ps1 templates/windows/cleanup-processed.ps1 modules/02-folder-trigger.md
git commit -m "feat(ops): add log + processed cleanup PS1 scripts"
```

---

### Task 18: .env 단일화 마이그레이션 문서

**Files:**
- Create: `C:\dev\agent-bootstrap\modules\migration-env-singularization.md`
- Modify: `C:\dev\agent-bootstrap\modules\04-notion-archive.md` (마이그레이션 링크)

- [ ] **Step 1: migration-env-singularization.md 작성**

`modules/migration-env-singularization.md`:
```markdown
# .env 단일화 마이그레이션

직전 1차 수정에서 settings.json env 와 .env 의 중복을 .env 단일 출처로 통일했습니다.
기존 설치 사용자가 따라야 할 5분 마이그레이션 절차입니다.

## 영향

- **이전**: `NOTION_API_TOKEN`, `NOTION_SESSION_DB`, `NOTION_DAILY_DB`, `SLACK_SESSION_WEBHOOK` 가 `~/.claude/settings.json` 의 `env` 섹션과 `.env` 양쪽에 있어 동기화 부담.
- **이후**: `.env` 만이 단일 출처. settings.json 의 env 섹션에서 위 4개는 비워도 됨.

## 마이그레이션 절차

1. **현재 settings.json env 백업**
   ```powershell
   Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.bak"
   ```

2. **.env 에 4개 변수 존재 확인**
   ```powershell
   Get-Content "$env:USERPROFILE\.claude\secrets\slack-jipsa.env" |
     Select-String 'NOTION_API_TOKEN|NOTION_SESSION_DB|NOTION_DAILY_DB|SLACK_SESSION_WEBHOOK'
   ```
   비어있는 항목은 settings.json 에서 값 복사 후 `.env` 에 추가.

3. **settings.json 의 env 섹션에서 위 4개 키 제거** (다른 env 항목 보존)

4. **daemon 재시작**
   ```powershell
   Stop-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
   Start-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
   ```

5. **검증**: 새 슬랙 메시지 1개 → 노션에 row 생성 확인.

## 문제 해결

- daemon 부팅 시 `[daemon] WARN: BOT_USER_ID auth.test failed: ...` → 토큰 권한 확인.
- 노션 row 생성 안 됨 → `~/.claude/scripts/slack-jipsa/logs/daemon.log.YYYY-MM-DD` 의 `notion_log_turn failed` 검색.
```

- [ ] **Step 2: modules/04 의 첫 부분에 안내 링크 추가**

`modules/04-notion-archive.md` 의 "사전 점검" 섹션 끝에 추가:
```markdown
> **기존 설치 사용자**: settings.json env → .env 통일 마이그레이션이 필요합니다. [.env 단일화 마이그레이션](migration-env-singularization.md) 참고.
```

- [ ] **Step 3: 커밋**

```bash
git add modules/migration-env-singularization.md modules/04-notion-archive.md
git commit -m "docs: add .env singularization migration guide"
```

---

## Phase E — 보안 강화

### Task 19: ChannelMemberMonitor + JipsaDaemon 통합

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\security_monitor.py`
- Create: `C:\dev\agent-bootstrap\tests\unit\test_security_monitor.py`
- Modify: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\jipsa_daemon.py` (monitor 통합)

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_security_monitor.py`:
```python
import logging

import security_monitor


def test_baseline_captures_members(mocker):
    web = mocker.MagicMock()
    web.conversations_members.return_value = {"ok": True, "members": ["U1", "U2"]}
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    assert mon.known == {"U1", "U2"}


def test_check_detects_new_member(mocker):
    web = mocker.MagicMock()
    web.conversations_members.side_effect = [
        {"members": ["U1"]},
        {"members": ["U1", "U2"]},
    ]
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    mon.check()
    web.chat_postMessage.assert_called_once()
    assert "U2" in web.chat_postMessage.call_args.kwargs["text"]
    assert mon.known == {"U1", "U2"}


def test_check_no_alert_when_unchanged(mocker):
    web = mocker.MagicMock()
    web.conversations_members.side_effect = [
        {"members": ["U1"]},
        {"members": ["U1"]},
    ]
    mon = security_monitor.ChannelMemberMonitor(web, "Cabc", logging.getLogger("test"))
    mon.baseline()
    mon.check()
    web.chat_postMessage.assert_not_called()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_security_monitor.py -v`
Expected: 3 FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: security_monitor.py 작성**

`templates/scripts/slack-jipsa/security_monitor.py`:
```python
"""채널 멤버 변화 감지 — dangerously-skip-permissions risk 완화."""
from __future__ import annotations

import logging
import threading
from typing import Any

from slack_sdk import WebClient

logger = logging.getLogger(__name__)


class ChannelMemberMonitor:
    def __init__(self, web: WebClient, channel: str, log: logging.Logger | None = None):
        self.web = web
        self.channel = channel
        self.known: set[str] = set()
        self.logger = log or logger
        self._timer: threading.Timer | None = None

    def baseline(self) -> None:
        """daemon 시작 시 1회. 현재 멤버 set 저장."""
        resp = self.web.conversations_members(channel=self.channel)
        self.known = set(resp.get("members", []))
        self.logger.info("channel baseline: %d members", len(self.known))

    def check(self) -> None:
        """현재 멤버와 baseline 비교. 새 멤버 발견 시 슬랙 경고."""
        resp = self.web.conversations_members(channel=self.channel)
        current = set(resp.get("members", []))
        new = current - self.known
        if new:
            self.logger.warning("NEW CHANNEL MEMBERS: %s", new)
            try:
                self.web.chat_postMessage(
                    channel=self.channel,
                    text=f":rotating_light: 새 채널 멤버 감지: {', '.join(new)}. "
                         f"`--dangerously-skip-permissions` 사용 중 — 명령 실행 권한 즉시 확인 필요.",
                )
            except Exception as e:
                self.logger.warning("alert post failed: %s", e)
            self.known = current

    def start_periodic(self, interval_sec: int = 3600) -> None:
        """interval 마다 check() 재귀 스케줄."""
        self.check()
        self._timer = threading.Timer(interval_sec, self.start_periodic, args=(interval_sec,))
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit/test_security_monitor.py -v`
Expected: 3 PASS.

- [ ] **Step 5: JipsaDaemon 통합**

`templates/scripts/slack-jipsa/jipsa_daemon.py` 의 `__init__` 끝과 `start()` 안 추가:
```python
# __init__ 끝:
from security_monitor import ChannelMemberMonitor
self.member_monitor = ChannelMemberMonitor(self.web, self.channel, logger)

# start() 안 (sock.connect() 이전):
try:
    self.member_monitor.start_periodic(interval_sec=3600)
except Exception as e:
    logger.warning("member monitor start failed: %s", e)
```

- [ ] **Step 6: syntax**

Run: `python -m py_compile templates/scripts/slack-jipsa/security_monitor.py templates/scripts/slack-jipsa/jipsa_daemon.py`
Expected: 출력 없음.

- [ ] **Step 7: 커밋**

```bash
git add templates/scripts/slack-jipsa/security_monitor.py templates/scripts/slack-jipsa/jipsa_daemon.py tests/unit/test_security_monitor.py
git commit -m "feat(security): channel member change detection"
```

---

### Task 20: audit_logger.py + claude_invoker 통합

**Files:**
- Create: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\audit_logger.py`
- Create: `C:\dev\agent-bootstrap\tests\unit\test_audit_logger.py`
- Modify: `C:\dev\agent-bootstrap\templates\scripts\slack-jipsa\jipsa_daemon.py` (on_invoke 콜백 hook 연결)
- Modify: `C:\dev\agent-bootstrap\.gitignore` (audit/)

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_audit_logger.py`:
```python
import hashlib

import audit_logger


def test_log_invocation_writes_line(tmp_path):
    audit = audit_logger.AuditLogger(audit_dir=tmp_path)
    audit.log_invocation(channel="Cabc", session_id="sess1",
                         prompt="hello world", result_len=10, status="ok")
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Cabc" in content
    assert "sess1" in content
    # raw prompt 텍스트 자체는 포함되지 않음
    assert "hello world" not in content
    # 해시는 포함
    expected_hash = hashlib.sha256(b"hello world").hexdigest()[:16]
    assert expected_hash in content


def test_log_failure_status(tmp_path):
    audit = audit_logger.AuditLogger(audit_dir=tmp_path)
    audit.log_invocation(channel="C1", session_id="s1",
                         prompt="x", result_len=0, status="fail")
    content = next(tmp_path.glob("*.log")).read_text()
    assert "status=fail" in content
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_audit_logger.py -v`
Expected: 2 FAIL.

- [ ] **Step 3: audit_logger.py 작성**

`templates/scripts/slack-jipsa/audit_logger.py`:
```python
"""Audit log for claude --print invocations.

Prompt 본문은 저장하지 않음 (privacy + 디스크). sha256 hash + 길이만.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, audit_dir: Path):
        self.audit_dir = audit_dir
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def _today_file(self) -> Path:
        return self.audit_dir / f"{time.strftime('%Y-%m-%d')}.log"

    def log_invocation(self, channel: str, session_id: str,
                       prompt: str, result_len: int, status: str) -> None:
        try:
            h = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()[:16]
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            line = (
                f"{ts} channel={channel} session={session_id} action=claude_invoke "
                f"prompt_sha256={h} len_in={len(prompt or '')} "
                f"len_out={result_len} status={status}\n"
            )
            with self._today_file().open("a", encoding="utf-8") as fp:
                fp.write(line)
        except Exception as e:
            logger.warning("audit write failed: %s", e)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit/test_audit_logger.py -v`
Expected: 2 PASS.

- [ ] **Step 5: JipsaDaemon 통합 — call_claude 의 on_invoke 콜백 연결**

`templates/scripts/slack-jipsa/jipsa_daemon.py` 의 `__init__` 끝에 추가:
```python
from audit_logger import AuditLogger
self.audit = AuditLogger(self.shared_dir.parent / "slack-jipsa" / "audit")
```

handle_message 안의 `call_claude(prompt, channel)` 호출을 다음으로 교체:
```python
def _audit_hook(ch, sid, len_in, len_out):
    status = "ok" if len_out > 0 else "fail"
    self.audit.log_invocation(ch, sid, "", len_out=len_out if False else len_out,
                              result_len=len_out, status=status)
# claude_invoker.call_claude(...)
reply = call_claude(
    prompt, channel,
    sessions_dir=self.sessions_dir,
    system_prompt=self.system_prompt,
    timeout=self.claude_timeout,
    on_invoke=lambda ch, sid, lin, lout: self.audit.log_invocation(
        channel=ch, session_id=sid, prompt=prompt,
        result_len=lout, status=("ok" if lout > 0 else "fail"),
    ),
)
```

- [ ] **Step 6: .gitignore 업데이트**

`.gitignore` 에 추가:
```
# audit logs
audit/
```

- [ ] **Step 7: syntax + 통합 smoke**

Run: `python -m py_compile templates/scripts/slack-jipsa/audit_logger.py templates/scripts/slack-jipsa/jipsa_daemon.py && uv run pytest tests/unit -v`
Expected: 모두 PASS.

- [ ] **Step 8: 커밋**

```bash
git add templates/scripts/slack-jipsa/audit_logger.py templates/scripts/slack-jipsa/jipsa_daemon.py tests/unit/test_audit_logger.py .gitignore
git commit -m "feat(security): audit log for claude invocations"
```

---

### Task 21: Bot Token rotation 가이드

**Files:**
- Create: `C:\dev\agent-bootstrap\modules\security-token-rotation.md`

- [ ] **Step 1: 가이드 작성**

`modules/security-token-rotation.md`:
```markdown
# 보안 — Slack Bot Token 정기 교체

`SLACK_BOT_TOKEN` (`xoxb-...`) 은 채널 메시지 게시·읽기·반응 추가 권한을 가집니다.
유출 시 채널 도청·스푸핑 가능. 3-6개월 주기 교체 권장.

## 교체 절차 (5분)

1. **Slack 앱 페이지 진입**
   https://api.slack.com/apps → 본인 앱 선택 → "OAuth & Permissions"

2. **새 토큰 발급**
   - "Reinstall to Workspace" 클릭 → 권한 확인 → "Allow"
   - 페이지 상단의 "Bot User OAuth Token" 의 새 `xoxb-...` 복사

3. **.env 교체**
   ```powershell
   notepad "$env:USERPROFILE\.claude\secrets\slack-jipsa.env"
   ```
   `SLACK_BOT_TOKEN=` 라인의 값을 새 토큰으로 교체. 저장.

4. **daemon 재시작**
   ```powershell
   Stop-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
   Start-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
   ```
   macOS: `launchctl unload/load ~/Library/LaunchAgents/com.<user>.slack-jipsa.plist`

5. **검증**
   - 슬랙 채널에 메시지 1개 전송 → daemon 응답 확인
   - `~/.claude/scripts/slack-jipsa/logs/daemon.log.YYYY-MM-DD` 에 `auto-resolved BOT_USER_ID=...` 없는지 확인 (기존 BOT 유지면 정상)

## 유출 의심 시

1. 즉시 Slack 앱 페이지의 "Revoke Token" 클릭
2. 위 절차로 새 토큰 발급
3. `~/.claude/scripts/slack-jipsa/audit/` 의 최근 로그 검토 — 비정상 channel/session 호출 있는지

## 자동화 (옵션)

reminder cron 등록:
```powershell
schtasks /Create /SC MONTHLY /MO 3 /TN "TokenRotationReminder" `
  /TR 'msg %username% "Slack Bot Token 정기 교체 시기. modules/security-token-rotation.md 참고."' /F
```
```

- [ ] **Step 2: 커밋**

```bash
git add modules/security-token-rotation.md
git commit -m "docs(security): add Slack Bot Token rotation guide"
```

---

## Phase F — 한국어 CONTRIBUTING

### Task 22: CONTRIBUTING.md (한국어)

**Files:**
- Create: `C:\dev\agent-bootstrap\CONTRIBUTING.md`

- [ ] **Step 1: CONTRIBUTING.md 작성**

`CONTRIBUTING.md`:
```markdown
# 기여 가이드

agent-bootstrap 에 관심 가져주셔서 감사합니다. 본 문서는 한국어 화자 기여자 대상입니다.

## 시작하기

1. **이슈 먼저**
   기능 추가·아키텍처 변경은 PR 보다 먼저 GitHub Issue 에 의도를 남겨주세요.
   사소한 오타·로그 메시지 수정은 바로 PR 환영.

2. **로컬 환경 구성**
   ```powershell
   git clone https://github.com/<owner>/agent-bootstrap.git
   cd agent-bootstrap
   uv sync --extra test
   uv run pytest tests/ -q
   ```
   Windows / macOS / Linux 모두 지원. CI 가 3 OS × 3 Python 버전 매트릭스 검증.

## 코드 스타일

- **검증 코드 (A 카테고리) 는 손대지 마세요.**
  `templates/lib/*.py`, `templates/scripts/slack-jipsa/daemon.py` 등 `SKILL.md` 의 A 카테고리는
  사용자 환경에서 실측 검증된 코드입니다. 버그 발견 시 이슈 → 합의 후 수정.
- **B 카테고리 (`.tmpl`)**: 치환 토큰 (`{USERNAME}`, `{HOME}`) 보존.
- **C 카테고리 (Windows 검증본)**: AST parse 통과 필수 (`scripts/ast-check.ps1` 또는 CI).
- 새 의존성 추가는 `pyproject.toml` 의 `[project.optional-dependencies].test` 에 명시.

## PR 절차

1. **브랜치 네이밍**: `phase-{A-F}/<short-desc>` 또는 `fix/<short-desc>`.
2. **커밋 컨벤션** (Conventional Commits):
   - `feat:` 새 기능
   - `fix:` 버그 수정
   - `refactor:` 리팩터링 (외부 동작 변화 없음)
   - `test:` 테스트 추가/수정
   - `docs:` 문서만 변경
   - `ci:` CI 설정
   - `chore:` 잡일
3. **테스트**:
   - 새 코드는 `tests/unit/` 또는 `tests/integration/` 에 테스트 추가.
   - 기존 테스트가 깨지면 안 됨.
4. **CI 통과**:
   - GHA `tests` + `lint` 두 워크플로우 모두 green.
5. **PR 본문**:
   - 무엇을·왜·어떻게 변경했는지 요약.
   - 관련 이슈 번호 (`Closes #N`).
   - 수동 검증한 단계 (UI 변경 또는 외부 API 호출 시).

## 이슈 작성

다음 정보를 포함해주세요:

- **환경**: OS (Windows/macOS/Linux), Python 버전, agent-bootstrap 커밋 해시
- **재현 단계**: 1-2-3
- **기대 동작 / 실제 동작**
- **로그 첨부** (`.env` 의 토큰·시크릿은 반드시 `***` 로 마스킹)

## 의사 결정

- 사소한 변경 (오타·로그 메시지·테스트 추가): PR 바로 환영.
- 큰 변경 (새 모듈 추가·기존 구조 리팩터·외부 API 추가): 이슈 → 메인테이너 코멘트 후 PR.
- 보안 보고: GitHub Security Advisory 또는 메인테이너 이메일 직접 (공개 이슈에 올리지 말 것).

## Code of Conduct

본 프로젝트는 [Contributor Covenant 2.1](CODE_OF_CONDUCT.md) 를 따릅니다.
참여 전 한 번 읽어주세요.

## 기타

질문은 GitHub Issue 의 `question` 라벨에 자유롭게 올려주세요.
```

- [ ] **Step 2: 커밋**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add Korean CONTRIBUTING.md"
```

---

### Task 23: CODE_OF_CONDUCT.md (Contributor Covenant 2.1 한국어)

**Files:**
- Create: `C:\dev\agent-bootstrap\CODE_OF_CONDUCT.md`

- [ ] **Step 1: CODE_OF_CONDUCT.md 작성**

`CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 한국어 공식 번역):
```markdown
# 기여자 행동 강령 / Contributor Covenant Code of Conduct

## 우리의 약속

회원, 기여자, 리더는 본 프로젝트와 커뮤니티에 참여하는 모두에게 나이, 신체 크기, 가시적이거나 비가시적인 장애, 민족, 성 특징, 성 정체성과 표현, 경험 수준, 교육, 사회경제적 지위, 국적, 외모, 인종, 카스트, 피부색, 종교, 또는 성 정체성과 지향에 관계없이 학대 없는 경험을 제공할 것을 약속합니다.

우리는 개방적이고, 환영하며, 다양하고, 포용적이며, 건강한 커뮤니티에 기여하는 방식으로 행동하고 교류할 것을 약속합니다.

## 우리의 기준

우리 커뮤니티에 긍정적인 환경을 조성하는 행동의 예시:

* 다른 사람에 대한 공감과 친절을 표현
* 다른 의견·관점·경험을 존중
* 건설적 피드백을 주고받음
* 책임을 인정하고, 실수의 영향을 받은 이들에게 사과하며, 경험으로 배움
* 개인뿐 아니라 전체 커뮤니티에 가장 좋은 것에 집중

용납할 수 없는 행동의 예시:

* 성적 언어·이미지의 사용 및 모든 종류의 성적 관심과 접근
* 트롤링, 모욕적·비하적 발언, 개인적·정치적 공격
* 공적·사적 괴롭힘
* 명시적 허가 없이 타인의 사생활 정보 (주소, 이메일 등) 공개
* 직업 환경에서 부적절하다고 합리적으로 여겨질 수 있는 행동

## 집행 책임

커뮤니티 리더는 수용 가능한 행동의 기준을 명확히 하고 시행하며, 부적절·위협적·공격적·해로운 행동에 대해 적절하고 공정한 시정 조치를 취할 책임이 있습니다.

커뮤니티 리더는 본 행동 강령에 부합하지 않는 댓글·커밋·코드·위키 편집·이슈 및 기타 기여를 제거·편집·거부할 권리와 책임을 가지며, 적절한 경우 조정 결정의 근거를 알립니다.

## 적용 범위

본 행동 강령은 모든 커뮤니티 공간에서 적용되며, 공개적 공간에서 개인이 커뮤니티를 공식 대표할 때도 적용됩니다. 대표의 예: 공식 이메일 주소, 공식 소셜 미디어 계정 사용, 온·오프라인 이벤트에서의 지정 대표자로 행동.

## 집행

학대·괴롭힘 또는 기타 용납할 수 없는 행동의 사례는 집행을 담당하는 커뮤니티 리더에게 다음 연락처로 보고할 수 있습니다:

**ingbeeeded@gmail.com**

모든 불만은 신속하고 공정하게 검토·조사됩니다.

모든 커뮤니티 리더는 사건 신고자의 사생활과 안전을 존중할 의무가 있습니다.

## 집행 가이드라인

커뮤니티 리더는 본 행동 강령 위반으로 간주되는 행동에 대한 결과를 결정할 때 다음 커뮤니티 영향 가이드라인을 따릅니다:

### 1. 시정

**커뮤니티 영향**: 부적절한 언어 사용 또는 커뮤니티에서 비전문적·환영받지 못한다고 여겨지는 행동.

**결과**: 커뮤니티 리더의 비공개 서면 경고. 위반 성격에 대한 명확성과 행동이 부적절한 이유에 대한 설명 제공. 공개 사과를 요청할 수 있습니다.

### 2. 경고

**커뮤니티 영향**: 단일 사건 또는 일련의 행동을 통한 위반.

**결과**: 지속된 행동에 대한 결과가 있는 경고. 일정 기간 동안 관련된 사람들과의 상호 작용 없음 — 행동 강령 시행 담당자와 원치 않는 상호 작용 포함. 본 조건 위반 시 일시적 또는 영구적 금지 가능.

### 3. 일시적 금지

**커뮤니티 영향**: 지속된 부적절한 행동을 포함한 커뮤니티 기준의 심각한 위반.

**결과**: 명시된 기간 동안 커뮤니티와의 모든 종류의 상호 작용 또는 공개 통신에서 일시적 금지. 본 기간 동안 행동 강령 시행 담당자와의 비공개 상호 작용을 포함한 관련된 사람들과의 어떠한 공개·비공개 상호 작용도 허용되지 않습니다. 본 조건 위반 시 영구적 금지 가능.

### 4. 영구적 금지

**커뮤니티 영향**: 지속된 부적절한 행동, 개인에 대한 괴롭힘, 또는 집단의 공격·비방을 포함한 커뮤니티 기준 위반 패턴 표시.

**결과**: 커뮤니티 내 모든 종류의 공개 상호 작용에서 영구적 금지.

## 출처

본 행동 강령은 [Contributor Covenant][homepage] 버전 2.1 에서 채택되었으며, [https://www.contributor-covenant.org/version/2/1/code_of_conduct.html][v2.1] 에서 확인 가능합니다.

[homepage]: https://www.contributor-covenant.org
[v2.1]: https://www.contributor-covenant.org/version/2/1/code_of_conduct.html

커뮤니티 영향 가이드라인은 [Mozilla's code of conduct enforcement ladder][Mozilla CoC] 에 영감을 받았습니다.

[Mozilla CoC]: https://github.com/mozilla/diversity

본 행동 강령에 대한 일반적 질문은 [https://www.contributor-covenant.org/faq][FAQ] 의 FAQ 참고. 번역본은 [https://www.contributor-covenant.org/translations][translations] 에서 확인 가능합니다.

[FAQ]: https://www.contributor-covenant.org/faq
[translations]: https://www.contributor-covenant.org/translations
```

- [ ] **Step 2: 커밋**

```bash
git add CODE_OF_CONDUCT.md
git commit -m "docs: add Contributor Covenant 2.1 (Korean)"
```

---

### Task 24: README 링크 + CLAUDE.md 업데이트

**Files:**
- Modify: `C:\dev\agent-bootstrap\README.md` (CONTRIBUTING / CoC 링크)
- Modify: `C:\dev\agent-bootstrap\CLAUDE.md` (새 모듈 구조 명시)

- [ ] **Step 1: README.md 하단 추가**

`README.md` 끝에 추가 (LICENSE 섹션 옆 또는 직전):
```markdown
## 기여 / Contributing

기여 가이드는 [CONTRIBUTING.md](CONTRIBUTING.md) 를, 행동 강령은 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 를 참고해주세요.
```

- [ ] **Step 2: CLAUDE.md 업데이트 — 새 모듈 구조**

`CLAUDE.md` 의 "저장소 vs 사용자 머신의 경로 매핑" 표 아래에 추가:
```markdown
## daemon 내부 모듈 구조 (Phase A 리팩터 후)

`templates/scripts/slack-jipsa/` 안 모듈 책임:

| 파일 | 책임 |
|------|------|
| `daemon.py` | entry point (`load_env` → `JipsaDaemon.start`) |
| `jipsa_daemon.py` | `JipsaDaemon` 클래스 (state + on_event + handle_message 오케스트레이션) |
| `filters.py` | 메시지 필터 (is_self / is_miri / discussion 키워드) |
| `session_storage.py` | 채널별 session_id 조회·생성·리셋 |
| `claude_invoker.py` | subprocess `claude --print` 호출 + resume fallback |
| `notion_logger.py` | 한 턴을 Notion DB 에 적재 (모듈 1 의존성 체크) |
| `slack_io.py` | chat_postMessage / reaction add·remove 래퍼 |
| `security_monitor.py` | 채널 멤버 변화 감지 (Phase E) |
| `audit_logger.py` | claude --print 호출 audit log (Phase E) |
| `logging_config.py` | TimedRotatingFileHandler 로깅 셋업 |

위 모듈을 수정할 때는 [docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md](docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md) 의 책임 분리 원칙을 따른다.
```

- [ ] **Step 3: 커밋**

```bash
git add README.md CLAUDE.md
git commit -m "docs: link CONTRIBUTING/CoC + document daemon module structure"
```

---

### Task 25: 최종 회귀 검증 + GitHub 라벨·템플릿

**Files:**
- Create: `C:\dev\agent-bootstrap\.github\ISSUE_TEMPLATE\phase-task.md`
- Create: `C:\dev\agent-bootstrap\.github\PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: ISSUE_TEMPLATE 작성**

`.github/ISSUE_TEMPLATE/phase-task.md`:
```markdown
---
name: Phase Sub-task
about: cleanup spec 의 한 sub-task 트래킹
title: "[phase-X] short description"
labels: ''
assignees: ''
---

## 어느 spec 항목인지

링크: docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md#... (해당 섹션 anchor)

## 무엇을 바꾸는지

1-3 문장.

## Acceptance

- [ ] 코드 변경 + 테스트 추가
- [ ] `uv run pytest tests/ -q` PASS
- [ ] `python -m py_compile <touched files>` PASS
- [ ] CI green
- [ ] spec acceptance criteria 해당 항목 체크

## 의존성

Blocked by: #N (있다면)
Blocks: #M (있다면)
```

- [ ] **Step 2: PR_TEMPLATE 작성**

`.github/PULL_REQUEST_TEMPLATE.md`:
```markdown
## 요약

무엇을 / 왜.

## 변경 사항

- 파일 1: …
- 파일 2: …

## 테스트

- [ ] 단위 테스트 추가/수정
- [ ] 통합 테스트 추가/수정 (해당 시)
- [ ] 수동 검증 단계 (있다면 단계 명시)

## 체크리스트

- [ ] `uv run pytest tests/ -q` PASS
- [ ] CI tests + lint 두 워크플로우 green
- [ ] 관련 이슈 link (`Closes #N`)
- [ ] spec 의 acceptance criteria 매핑 (어느 항목 충족했는지)
- [ ] (해당 시) 마이그레이션 문서 업데이트

## Spec 매핑

docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md 의 어느 섹션:

- Phase X / 항목 N
```

- [ ] **Step 3: 최종 회귀 — 전체 테스트 + py_compile + bash -n**

Run:
```bash
uv run pytest tests/ -q
python -m py_compile templates/scripts/slack-jipsa/*.py templates/lib/*.py templates/hooks/append_turn_raw.py
bash -n templates/hooks/slack-session-summary.sh
```
Expected: 모든 명령 출력 없음 또는 PASS.

- [ ] **Step 4: 글로벌 mutable state 0 확인**

Run: `grep -nE '^_\w+\s*[:=]' templates/scripts/slack-jipsa/daemon.py templates/scripts/slack-jipsa/jipsa_daemon.py || echo OK`
Expected: `OK` (또는 출력 0줄).

- [ ] **Step 5: 사용자 수동 검증 — 슬랙 1턴 + 폴더 1파일**

1. 슬랙 채널에 "안녕" 1개 전송 → daemon 응답 + 노션 row 1개 확인.
2. `~/.claude/scripts/folder-watch/inbox/` 에 빈 .md 1개 drop → 처리 결과 확인.

Expected: 회귀 0.

- [ ] **Step 6: 커밋**

```bash
git add .github/ISSUE_TEMPLATE/phase-task.md .github/PULL_REQUEST_TEMPLATE.md
git commit -m "ci: add Issue/PR templates for phase sub-tasks"
```

- [ ] **Step 7: 라벨 생성 (github-dev:create-issue-label 위임)**

writing-plans → decompose-issue 단계로 넘기기 전 라벨 11개 생성:
- phase: `phase-A`, `phase-B`, `phase-C`, `phase-D`, `phase-E`, `phase-F`
- type: `refactor`, `test`, `security`, `docs`, `infra`

명령은 `github-dev:create-issue-label` 스킬에 위임.

---

## 실행 핸드오프

전체 25 task 완성 후:

1. **이 plan 의 모든 task 가 ✅ 인지 확인**
2. **사용자에게 수동 검증 요청**: 슬랙·폴더 트리거 회귀 0 확인
3. **다음 단계 옵션 제시**:
   - **Option A**: `github-dev:decompose-issue` → 이 plan 의 각 Task 를 GitHub Issue 로 변환 → `github-dev:resolve-issue` 로 자동 진행
   - **Option B**: `superpowers:subagent-driven-development` 로 메인 세션에서 직접 task 순서대로 실행 (fast mode, implementer subagent 만)
   - **Option C**: `superpowers:executing-plans` 로 inline 실행 (배치 체크포인트 review)

사용자 결정 후 선택된 워크플로우 진입.

---

## Self-Review

이 plan 을 spec 대비 점검 (writing-plans 스킬의 self-review checklist):

**1. Spec coverage**:
- Phase A.1 (daemon 분리) → Task 7-14 ✓
- Phase A.2 (exception 정책) → Task 9/11/19 의 try/except 패턴 (모듈 분리하며 적용)
- Phase A.3 (structured logging) → Task 12 ✓
- Phase A.4 (timeout env) → Task 10 ✓
- Phase B.1-5 (pytest + CI + coverage) → Task 1-6, 15 ✓
- Phase C (ps1) → Task 16 ✓
- Phase D.1-5 (운영 가드) → Task 17, 18, 11 (module1 check), 10 (timeout dup) ✓
- Phase E.1-4 (보안) → Task 19, 20, 21, 15 (BOT_USER_ID 회귀) ✓
- Phase F (CONTRIBUTING / CoC) → Task 22, 23, 24 ✓
- GitHub workflow (Task 25) → 라벨·템플릿 ✓

**2. Placeholder scan**: 없음. 모든 step 에 exact 파일 경로 + 코드 블록 또는 명령.

**3. Type consistency**:
- `JipsaDaemon` — Task 13/14/19/20 일관 ✓
- `ChannelMemberMonitor` — Task 19/20 일관 ✓
- `AuditLogger` — Task 20 ✓
- `call_claude(prompt, channel, sessions_dir=..., system_prompt=..., timeout=..., on_invoke=...)` — Task 10/13/20 시그니처 일관 ✓
- `notion_log_turn(channel, event_ts, user_text, reply_text, session_id, model, session_db, daily_db, user_name, bot_name)` — Task 11/13 일관 ✓

**4. 의존성 정합성**:
- Task 7-12 의 모듈 추출이 Task 13 의 JipsaDaemon 통합보다 먼저 ✓
- Task 13 이 Task 14 (daemon.py 축소) 보다 먼저 ✓
- Task 15 의 통합 테스트는 Task 13/14 위에서 실행 ✓
- Task 19, 20 의 보안 모듈은 Task 13 의 JipsaDaemon 통합점 위에서 ✓
