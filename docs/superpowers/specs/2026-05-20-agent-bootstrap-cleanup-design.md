# Spec: agent-bootstrap 코드베이스 cleanup (단일 spec · 6 Phase)

> **Status:** brainstorming → spec 확정 (2026-05-20). 다음 단계: writing-plans 가 이 spec 을 `docs/superpowers/plans/2026-05-20-agent-bootstrap-cleanup.md` 로 변환 → user review → github-dev:decompose-issue.

## Context

직전 세션에서 11개 약점을 1차 수정했으나 (커밋 안 됨, working tree 에 보존), 본인 학습용 검토 결과 21개 약점 추가 식별. 사용자는 단일 spec/plan 으로 통째 진행 결정. GitHub 공개 + 한국어 타겟 청중.

## 사용자 결정 (AskUserQuestion 합의)

1. **청중**: GitHub 공개 오픈소스, 한국어 화자 타겟 (영어 fallback·i18n 0)
2. **spec 구조**: 단일 spec, sub-project 분해 X, 6 Phase 순차 (Phase A → F)
3. **Phase A 글로벌 state 격리**: 클래스 인스턴스 캡슐화 (`JipsaDaemon` 클래스, instance attr 로 이동)
4. **Phase E 보안 보강**: 3종 모두 (채널 멤버 변화 감지 + Bot Token rotation 가이드 + Audit log)
5. **위쪽 11개 1차 수정**: 그대로 보존, 이번 작업은 그 위에 누적

## 의존성 그래프

```
[B notion.py 단위 테스트]   <-- self-contained, 가장 먼저 시작 가능
        |
        v
[A handle_message 분리]     <-- B의 가벼운 부분 깔린 뒤 안전하게 진행
        |
        v
[B handle_message 통합 테스트]  <-- A로 분리된 함수들 테스트
        |
        +---> [C Windows ps1]   <-- A·B 일부 위에서 검증
        |
        +---> [D 운영 가드]     <-- A·B 위에서 logging 통합
        |
        v
[E 보안]                    <-- D의 audit log + B의 테스트로 검증
        |
        v
[F CONTRIBUTING]            <-- 마지막 마무리
```

## 데이터 흐름 / 아키텍처 영향

**불변**: Slack → daemon → claude CLI → Slack/Notion 데이터 흐름 그대로. 외부 API 호출 패턴 변화 없음. 변경되는 건 daemon **내부 코드 구조** + **운영 가드** + **검증 인프라**.

**바뀌는 것**:
- `daemon.py` 모듈-level 함수 + 글로벌 state → `JipsaDaemon` 클래스 + 보조 모듈 (`filters.py`, `session_storage.py`, `notion_logger.py`)
- `print + 파일 append` 로깅 → `logging.handlers.TimedRotatingFileHandler`
- 사용자 검증 의존 → pytest + GitHub Actions 자동 회귀
- 익명 채널 멤버 변화 → 감지·경고 + audit trail

---

## Phase A — 코드 품질 / 리팩터

### A.1 `daemon.py` 분리

현재 `templates/scripts/slack-jipsa/daemon.py` 521줄 (1차 수정 후). `handle_message` 함수 (L348 시작) 만 150줄+. 단일 파일에 사용자 메시지 필터·라우팅·Claude 호출·Slack 응답·노션 적재·토론 모드까지 다 있음.

**목표 구조** (templates/scripts/slack-jipsa/ 폴더 안):

```
slack-jipsa/
├── daemon.py            ← entry point. JipsaDaemon 클래스 인스턴스화 + sock.connect()
├── jipsa_daemon.py      ← class JipsaDaemon: state + on_event + handle_message 오케스트레이션
├── filters.py           ← is_self / is_miri / is_other_bot / discussion 키워드 매칭
├── session_storage.py   ← get_or_create_session / reset_session / session_path
├── claude_invoker.py    ← _run_claude / call_claude (subprocess + fallback)
├── notion_logger.py     ← notion_log_turn (현재 daemon.py L259-345)
└── slack_io.py          ← chat_postMessage 래퍼, reaction add/remove, post_slack_safely
```

각 파일 100~150줄 이하 목표. `daemon.py` 자체는 30줄 이하로 축소 (import + main).

**`JipsaDaemon` 클래스**:
- `__init__(self, env: dict)` — ENV 로드 결과를 받음. instance attr 로:
  - `self.bot_token`, `self.app_token`, `self.channel`, `self.channel_dialog`
  - `self.miri`, `self.bot`, `self.user_name`, `self.bot_name`
  - `self.web = WebClient(...)`, `self.sock = SocketModeClient(...)`
  - `self.dialog_self_turn_count: int = 0`
  - `self.discussion_mode: dict[str, bool] = {}`
  - `self.shared_dir`, `self.sessions_dir`, `self.logs_dir`
  - `self.state_lock = threading.RLock()` ← discussion_mode·counter write 보호
- `on_event(self, client, req)` — ACK + handle_message 스레드 spawn
- `handle_message(self, event)` — 오케스트레이션만. 실제 로직은 filters / claude_invoker / notion_logger / slack_io 위임
- `start(self)` — auth.test 로 BOT auto-resolve (현재 L127-140) + sock.connect()

**삭제할 모듈-level 글로벌**: `_dialog_self_turn_count` (L241), `_discussion_mode` (L242), `web` (L161), `sock` (L162), `ENV` (L117) — 모두 `JipsaDaemon` instance attr 로 이동.

**보존할 모듈-level**: 상수 (`SECRETS`, `SESSIONS_DIR`, `LOGS_DIR`, `SHARED_DIR`, `SHARED_BUFFER_LIMIT=30`, `DIALOG_TURN_LIMIT=6`, regex 패턴들 `DISCUSSION_TRIGGER` L151, `DISCUSSION_STOP` L156).

### A.2 Exception 정책 통일

현재 `except Exception: pass` 가 11곳 이상. 일관 정책 없음.

**새 정책**:
- 시크릿/토큰 관련 → `log.exception("masked: %s", mask_secrets(str(e)))` 로 마스킹 + 기록
- 외부 API 실패 (Slack/Notion) → `log.warning("API failed: %s", e)` + 계속
- 파일 I/O 실패 (sessions/, shared/, logs/) → `log.warning(...)` + 계속
- 무조건 silent 가 정당한 곳 (reaction add/remove 같은 cosmetic) → `log.debug(...)` + pass
- 그 외 → bubble up

`mask_secrets` 는 `lib/notion.py:82` 의 함수 재사용 (이미 존재).

### A.3 Structured logging

현재 `log(msg: str)` 함수 (daemon.py L165-170) 가 print + 파일 append. level 구분 없음, JSON 아님, rotation 없음.

**새 logging 설정** (`logging_config.py` 신설):
```python
import logging, logging.handlers
def configure_logging(log_dir: Path, level: str = 'INFO'):
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / 'daemon.log', when='midnight', backupCount=30, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    handler.setFormatter(formatter)
    root = logging.getLogger('jipsa')
    root.addHandler(handler)
    root.setLevel(level)
```

호출처에서: `logger = logging.getLogger(__name__)` → `logger.info(...)`, `logger.warning(...)`.

기존 `log()` 함수는 즉시 logger wrapper 로 변경 (deprecation 한 사이클 X — 키트라 사용자 없음).

### A.4 subprocess timeout 환경변수화

현재 `daemon.py:222` `def call_claude(..., timeout: int = 900)` 하드코딩.

**변경**: `CLAUDE_TIMEOUT_SEC` env var (기본 900). `.env.example` 에 추가. `ENV.get('CLAUDE_TIMEOUT_SEC', '900')` 로 읽음.

---

## Phase B — 테스트 인프라

### B.1 pytest + uv 가상환경

**위치**: 키트 루트 `C:\dev\agent-bootstrap\` 에 `pyproject.toml` 추가 (현재 없음). `tests/` 폴더 신설.

`pyproject.toml`:
```toml
[project]
name = "agent-bootstrap-tests"
version = "0.1.0"
requires-python = ">=3.10"

[project.optional-dependencies]
test = ["pytest>=7.4", "pytest-cov>=4.1", "slack_sdk>=3.27", "pytest-mock>=3.12"]
```

`uv sync --extra test` 로 환경 구성.

### B.2 디렉토리 구조

```
tests/
├── conftest.py            # fixtures: mock WebClient, fake .jsonl transcript, tmp_path
├── unit/
│   ├── test_notion.py     # retry/backoff/mask_secrets/upsert_idempotency
│   ├── test_filters.py    # is_self / is_miri / is_other_bot / discussion 키워드
│   ├── test_session_storage.py   # get_or_create / reset / fallback
│   └── test_md_to_notion.py
└── integration/
    ├── test_handle_message.py   # mocked sock/web 으로 end-to-end 한 턴
    └── test_stop_hook.sh        # bats: slack-session-summary.sh
```

### B.3 fixture 패턴 (`conftest.py`)

```python
@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    # secrets/slack-jipsa.env 더미 생성
    ...
@pytest.fixture
def mock_web_client(mocker):
    # slack_sdk.WebClient 의 chat_postMessage 등 stub
    ...
@pytest.fixture
def fake_transcript(tmp_path):
    # ~/.claude/projects/<sid>.jsonl 모킹
    ...
```

### B.4 GitHub Actions CI

`.github/workflows/test.yml`:
```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ['3.10', '3.11', '3.12']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra test
      - run: uv run pytest tests/ -q --cov=templates --cov-report=term
      - run: python -m py_compile templates/scripts/slack-jipsa/*.py templates/lib/*.py templates/hooks/*.py
      - if: matrix.os != 'windows-latest'
        run: bash -n templates/hooks/slack-session-summary.sh
```

`.github/workflows/lint.yml`:
```yaml
name: lint
on: [push, pull_request]
jobs:
  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: shellcheck templates/hooks/*.sh
  pscheck:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - shell: pwsh
        run: |
          $err=$null;$t=$null
          Get-ChildItem templates/windows/*.ps1, templates/windows/*.ps1.tmpl |
            ForEach-Object {
              [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$err)|Out-Null
              if($err.Count -gt 0){throw "FAIL $($_.Name)"}
            }
```

### B.5 커버리지 목표

- `lib/notion.py`: 80%+ (retry/mask/upsert 모두 커버)
- `filters.py`, `session_storage.py`: 90%+ (작은 모듈, 모든 분기 커버 쉬움)
- `handle_message` 통합 테스트: 핵심 시나리오 5개 (일반 메시지·리셋·필터 통과·SKIP·notion 적재)
- 전체 50%+ (낮은 목표지만 0 → 50 가 가장 큰 점프)

---

## Phase C — Windows `slack-session-summary.ps1` 검증본

### C.1 위치

`templates/windows/slack-session-summary.ps1` 신설. D 카테고리 (AI 즉석 번역) → A 카테고리 (검증본 그대로 카피) 승격.

### C.2 sh → PowerShell 정밀 번역 매핑

| sh 원본 | PowerShell 번역 |
|--------|----------------|
| `set -uo pipefail` | `$ErrorActionPreference = 'Stop'; Set-StrictMode -Version Latest` |
| `if [[ "${X:-0}" == "1" ]]; then ...` | `if ($env:X -eq '1') { ... }` |
| `export SLACK_HOOK_RUNNING=1` | `$env:SLACK_HOOK_RUNNING = '1'` |
| `source ~/.claude/secrets/slack-jipsa.env` | `.env 파싱 함수 (이미 run-daemon.ps1 패턴 재사용)` |
| `STDIN_JSON=$(cat)` | `$STDIN_JSON = [Console]::In.ReadToEnd()` |
| `jq -r '.session_id // empty'` | `$obj = $STDIN_JSON \| ConvertFrom-Json; $sid = $obj.session_id` |
| `find ~/.claude/projects -name "*.jsonl"` | `Get-ChildItem "$env:USERPROFILE\.claude\projects" -Filter "*.jsonl" -Recurse` |
| `jq -rs '...turn 추출...'` | `Get-Content $t \| ForEach-Object { $_ \| ConvertFrom-Json } \| Where-Object { $_.type -eq 'user' } \| Select-Object -Last 1` |
| `curl -sS -X POST $SLACK_URL -d $payload` | `Invoke-RestMethod -Uri $SLACK_URL -Method Post -Body $payload -ContentType 'application/json'` |
| `curl ... chat.postMessage -H "Authorization: Bearer $TOKEN"` | `Invoke-RestMethod ... -Headers @{ Authorization = "Bearer $env:SLACK_BOT_TOKEN" }` |
| `python3 -` (heredoc → urllib) | `Invoke-RestMethod` 직접 (Python 의존 제거) |
| `sed -E 's/\*\*([^*]+)\*\*/*\1*/g'` | `-replace '\*\*([^*]+)\*\*', '*$1*'` |
| `notion_trim()` (head -c 1900) | `if ($s.Length -gt 1900) { $s.Substring(0,1900) } else { $s }` |

### C.3 jq query 정밀 번역

가장 복잡한 부분: sh L51-64 의 turn index 계산, L69-89 의 model 추출, L104-185 의 turn data 추출.

PowerShell 에서:
- `.jsonl` 한 줄씩 `ConvertFrom-Json` 으로 객체화
- `.type == 'user'` 만 필터 + `.message.content` 정규화 + `<task-notification>` 시작 제외 = `is_real_user`
- 마지막 real_user 이후 객체들만 추출
- assistant 의 `.message.content[].type == 'tool_use'` → name 수집
- `summarize_names` 는 PowerShell `Group-Object -Property name` + 카운트

### C.4 검증

1. AST parse: 이미 register-task.ps1 패턴으로 자동화 (`B.4` lint workflow 가 포함)
2. 사용자 본인 Windows 환경에서 실제 `claude --print "1+1"` 실행 후 슬랙 보고 도착 확인
3. transcript 가 모킹된 `tests/integration/test_stop_hook_ps1.ps1` (Pester 사용 가능하면)

### C.5 호환성

기존 sh 버전 보존 (macOS/Linux). modules/01 의 Windows 분기 안내에 새 `templates/windows/slack-session-summary.ps1` 가리키도록 변경. SKILL.md 의 "D. AI 책임 — Windows Stop hook 만 즉석 생성" 섹션 삭제 (C 카테고리에 흡수).

---

## Phase D — 운영 가드

### D.1 로그 회전

- `daemon.py` 의 logging: `TimedRotatingFileHandler(when='midnight', backupCount=30)` — 30일치 유지 후 자동 삭제 (A.3 와 함께)
- `folder-watch.ps1` / `folder-watch.sh`: 매일 다른 파일이라 자동 회전. 단 누적 정리 cron 또는 task 1개 추가
- `templates/windows/cleanup-old-logs.ps1` 신설 — `Get-ChildItem -Path logs/ -OlderThan 30Days` 식

### D.2 `.processed/` 자동 정리

`templates/windows/cleanup-processed.ps1`: 90일 이상 된 파일 삭제 (사용자 confirm 옵션). modules/02 안전 규칙에 cron 등록 안내 추가.

### D.3 모듈 의존성 런타임 체크

`notion_logger.py` 시작부:
```python
def _verify_module1_setup() -> bool:
    """모듈 4는 모듈 1 의존. .env + lib + hook 존재 확인."""
    required = [
        Path.home() / '.claude/secrets/slack-jipsa.env',
        Path.home() / '.claude/scripts/lib/notion.py',
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        logger.error(f'모듈 1 미완료. 누락: {missing}. modules/01-slack-bridge.md 진행 필요')
        return False
    return True
```

`notion_log_turn` 첫 줄에서 호출. 누락이면 silent return (현재처럼 NOTION_SESSION_DB 빈 값 체크와 함께).

### D.4 .env 단일화 마이그레이션 가이드

`modules/migration-env-singularization.md` 신설 (가벼운 문서). 직전 11개 1차 수정에서 settings.json env → .env 통일했음. 기존 사용자가 어떻게 옮기는지:

```markdown
# .env 단일화 마이그레이션

## 영향
- 이전: NOTION_API_TOKEN 등이 settings.json env + .env 양쪽에 있어 동기화 부담
- 이후: .env 만이 단일 출처. settings.json env 섹션은 비워도 됨

## 마이그레이션 (5분)
1. `~/.claude/settings.json` 의 env 섹션 backup
2. NOTION_API_TOKEN·NOTION_SESSION_DB·NOTION_DAILY_DB·SLACK_SESSION_WEBHOOK 가 .env 에도 있는지 확인 (없으면 .env 에 추가)
3. settings.json env 섹션에서 위 4개 제거 (다른 env 항목은 보존)
4. daemon 재시작: `Stop-ScheduledTask -TaskName AgentBootstrap-SlackDaemon; Start-ScheduledTask -TaskName AgentBootstrap-SlackDaemon`
5. 검증: 새 슬랙 메시지 1개 → 노션에 row 생성되는지 확인
```

### D.5 subprocess timeout 환경변수화

(A.4 와 동일 작업. Phase D 에서 modules/01 의 .env.example 안내 추가.)

---

## Phase E — 보안 강화

### E.1 Slack 채널 멤버 변화 감지

**왜**: `--dangerously-skip-permissions` 사용 — 채널 멤버 = 명령 실행 권한자. 본인만 멤버여야 함. 누가 join 하면 즉시 인지 필요.

**구현** (`security_monitor.py` 신설):
```python
class ChannelMemberMonitor:
    def __init__(self, web: WebClient, channel: str, logger):
        self.web = web
        self.channel = channel
        self.known = set()  # 처음 부팅 시 채워짐
        self.logger = logger

    def baseline(self):
        """daemon 시작 시 1회. 현재 멤버 목록을 known 으로 저장."""
        resp = self.web.conversations_members(channel=self.channel)
        self.known = set(resp['members'])
        self.logger.info(f'channel baseline: {len(self.known)} members')

    def check(self):
        """매 1시간. 새 멤버 발견 시 슬랙 + audit log 에 경고."""
        resp = self.web.conversations_members(channel=self.channel)
        current = set(resp['members'])
        new = current - self.known
        if new:
            self.logger.warning(f'NEW CHANNEL MEMBERS: {new}')
            self.web.chat_postMessage(
                channel=self.channel,
                text=f':rotating_light: 새 멤버 감지: {new}. 명령 실행 권한 확인 필요.')
            self.known = current
```

`JipsaDaemon.start()` 에서 `baseline()` 호출 + `threading.Timer(3600, self.check_members).start()` 재귀.

### E.2 Bot Token rotation 가이드

`modules/security-token-rotation.md` 신설. 주기적 (3-6개월) 토큰 재발급 절차:
1. Slack 앱 페이지 → OAuth → Reinstall
2. 새 xoxb-... 토큰 받기
3. `.env` 의 `SLACK_BOT_TOKEN` 교체
4. daemon 재시작
5. 검증

### E.3 Audit log

모든 `claude --print` 호출의 입력 메시지를 `~/.claude/scripts/slack-jipsa/audit/<date>.log` 에 적재:
```
2026-05-20T10:23:45 channel=C0AAA user=U0BBBBBB action=claude_invoke
  prompt_hash=sha256:abc123... session_id=def456...
  result_status=ok len_in=42 len_out=1024
```

prompt 본문 자체는 적재하지 않음 (privacy + 디스크). sha256 hash + 길이만. session_id + ts 로 transcript .jsonl 와 cross-reference 가능.

`audit_logger.py` 신설. `claude_invoker.py` 의 `call_claude` 안에서 호출.

### E.4 직전 수정의 BOT_USER_ID 자동 조회 회귀 확인

1차 수정 (이번 세션 직전)에 daemon.py L127-140 에 추가한 auth.test 자동 조회 + .env write-back 로직. 실행 검증 0. Phase B 통합 테스트로 회귀 확인:

```python
def test_bot_user_id_auto_resolve(fake_env, mock_web_client):
    fake_env['BOT_USER_ID'] = ''
    mock_web_client.auth_test.return_value = {'user_id': 'U0FAKE'}
    daemon = JipsaDaemon(fake_env)
    assert daemon.bot == 'U0FAKE'
    # .env 파일에 write-back 확인
    assert 'BOT_USER_ID=U0FAKE' in (fake_env_path).read_text()
```

---

## Phase F — 한국어 CONTRIBUTING

### F.1 `CONTRIBUTING.md` (한국어)

- 이슈 올리는 법 (재현 단계 + .env mask 한 로그 첨부 안내)
- PR 절차 (브랜치 네이밍, 커밋 메시지, 테스트 통과)
- 로컬 테스트 (`uv sync --extra test && uv run pytest`)
- 코드 스타일 (검증 코드 A 카테고리 수정 금지 룰 반복)
- 의사 결정 정책 (큰 변경은 issue 먼저)

### F.2 `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 한국어 번역)

표준 본문 그대로. 연락처 = repo 메인테이너 (Code of Conduct 본문의 placeholder 자리에 maintainer 가 본인 채널을 채움).

### F.3 README 하단 링크

```markdown
## 기여 / Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
```

영어 fallback X (청중 한국어 결정).

---

## Critical Files (수정 / 생성)

### 생성 (write)
- `pyproject.toml` (루트)
- `tests/conftest.py`
- `tests/unit/test_notion.py`
- `tests/unit/test_filters.py`
- `tests/unit/test_session_storage.py`
- `tests/unit/test_md_to_notion.py`
- `tests/integration/test_handle_message.py`
- `tests/integration/test_stop_hook.sh` (bats)
- `.github/workflows/test.yml`
- `.github/workflows/lint.yml`
- `.github/ISSUE_TEMPLATE/phase-task.md` (Step 3 sub-task 표준 양식)
- `.github/PULL_REQUEST_TEMPLATE.md` (체크리스트: 테스트·CI·spec 매핑)
- `docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md` (이 spec 본문)
- `templates/scripts/slack-jipsa/jipsa_daemon.py` (class)
- `templates/scripts/slack-jipsa/filters.py`
- `templates/scripts/slack-jipsa/session_storage.py`
- `templates/scripts/slack-jipsa/claude_invoker.py`
- `templates/scripts/slack-jipsa/notion_logger.py`
- `templates/scripts/slack-jipsa/slack_io.py`
- `templates/scripts/slack-jipsa/security_monitor.py`
- `templates/scripts/slack-jipsa/audit_logger.py`
- `templates/scripts/slack-jipsa/logging_config.py`
- `templates/windows/slack-session-summary.ps1` (D → A 승격)
- `templates/windows/cleanup-old-logs.ps1`
- `templates/windows/cleanup-processed.ps1`
- `modules/migration-env-singularization.md`
- `modules/security-token-rotation.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`

### 수정 (edit)
- `templates/scripts/slack-jipsa/daemon.py` → 30줄 entry point 로 축소
- `templates/hooks/slack-session-summary.sh` → audit_logger 호출 추가 (E.3)
- `modules/01-slack-bridge.md` → Windows slack-session-summary.ps1 안내, .env.example timeout 추가
- `modules/02-folder-trigger.md` → cleanup-processed.ps1 cron 안내
- `modules/04-notion-archive.md` → migration-env-singularization.md 링크
- `SKILL.md` → "D. AI 책임 — Windows Stop hook" 섹션 삭제 (C 카테고리 흡수)
- `CLAUDE.md` → 새 모듈 구조 명시 (jipsa_daemon.py + 보조 모듈)
- `README.md` → CONTRIBUTING / CODE_OF_CONDUCT 링크
- `.env.example` → `CLAUDE_TIMEOUT_SEC=900` 주석과 함께 추가
- `.gitignore` → `audit/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `htmlcov/` 추가

### 수정 안 함
- `templates/lib/notion.py` (검증 코드 — 테스트만 추가)
- `templates/lib/slack_mrkdwn.py` (검증 코드)
- `templates/lib/md_to_notion.py` (검증 코드)
- `templates/hooks/append_turn_raw.py` (직전 1차 수정의 .env fallback 그대로)
- `templates/launchd-*.plist.tmpl` (macOS — 변화 없음)
- `templates/systemd-*.tmpl` (Linux — 변화 없음)

---

## Verification (Phase 별 acceptance criteria)

### Phase A
- [ ] `python -m py_compile templates/scripts/slack-jipsa/*.py` 통과
- [ ] `daemon.py` 30줄 이하
- [ ] `handle_message` 가 jipsa_daemon.py 안에 있고 60줄 이하
- [ ] 글로벌 mutable state grep 0건 (`grep -E '^_\w+\s*[:=]' daemon.py`)
- [ ] `from lib.slack_mrkdwn import to_mrkdwn` 등 import 경로 동일하게 유지
- [ ] 수동 검증: 슬랙 1턴 + 폴더 1파일 — 회귀 0

### Phase B
- [ ] `uv run pytest tests/ -q` 통과
- [ ] coverage `lib/notion.py` 80%+, `filters.py` 90%+, 전체 50%+
- [ ] GHA test.yml + lint.yml 첫 실행 green
- [ ] PR 작성 시 자동 회귀 검증 동작 확인

### Phase C
- [ ] `templates/windows/slack-session-summary.ps1` 존재 + AST parse OK
- [ ] Pester (또는 수동) 으로 mock transcript → Slack post 흐름 검증
- [ ] 사용자 본인 Windows 환경에서 1턴 실제 검증
- [ ] SKILL.md "D 카테고리" 섹션 삭제

### Phase D
- [ ] daemon 재시작 후 `logs/daemon.log.YYYY-MM-DD` 형식 회전 확인
- [ ] 31일 후 가장 오래된 파일 자동 삭제 (시간 의존 — 수동 시뮬 또는 backupCount 단위 테스트)
- [ ] `.processed/` cleanup 스크립트 dry-run 결과 확인
- [ ] modules/04 시작 시 모듈 1 누락 시 친절한 에러 로그
- [ ] `CLAUDE_TIMEOUT_SEC=60` env 로 짧게 설정 후 timeout 발생 확인

### Phase E
- [ ] daemon 시작 후 audit/<date>.log 파일 생성 + 1턴 후 entry 1개
- [ ] mock 채널에 새 멤버 추가 시 슬랙 경고 메시지 도착
- [ ] `BOT_USER_ID` 빈 .env 로 부팅 시 auth.test 자동 호출 + write-back 확인 (B.4 통합 테스트)
- [ ] modules/security-token-rotation.md 존재

### Phase F
- [ ] `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` 한국어 본문 존재
- [ ] README 하단 링크 동작
- [ ] GitHub UI 가 두 파일을 라이선스 옆에 표시 (LICENSE 와 비슷)

### 전체
- [ ] git diff 확인 — 11개 1차 수정 영역과 충돌 0
- [ ] sub-task 별 PR 단위로 분할 가능 (writing-plans 가 자동 분할)
- [ ] 각 PR 머지 후 main 에서 첫 실행 — 회귀 0

### GitHub workflow
- [ ] 라벨 11개 (phase 6 + type 5) 생성됨
- [ ] ISSUE_TEMPLATE / PULL_REQUEST_TEMPLATE 두 파일 존재
- [ ] decompose-issue 호출 후 GitHub Issues 15-25 개 자동 생성
- [ ] 각 이슈에 phase + type 라벨 부여 확인
- [ ] 의존성 관계 (`Blocked by #N`) 정확히 표시
- [ ] main 브랜치 보호 설정 활성 (직접 push 금지, CI 통과 필수)
- [ ] 첫 PR (Phase B notion.py 단위 테스트) 머지 → squash 1 커밋 확인
- [ ] post-merge 후 브랜치 로컬·원격 정리 확인
- [ ] milestone 진행률 sync (`github-dev:update-progress`)

---

## 비목표 (이번 작업에 포함 안 함)

- 영어 fallback README/SKILL.md (청중 한국어 결정)
- Notion 컬럼명 i18n (한국어 그대로)
- 모듈 자체 추가 (4 모듈 그대로, 새 모듈 추가 X)
- launchd/systemd 새 template 추가 (macOS/Linux 는 변화 없음)
- `--dangerously-skip-permissions` 자체 제거 (자동화 본질 — E 의 보강으로 risk 완화)
- 사용량 통계 / privacy notice (별도 검토 필요, 이번 범위 X)
- 영문 Code of Conduct
- daemon 의 멀티 봇 토론 모드 제거 (사용자 정책 결정 영역, 코드 정리만)

---

## 실행 순서 (spec → writing-plans → decompose-issue → resolve-issue)

### Step 1. Spec 파일 확정 (이 문서) ✓
- 이 spec 을 `docs/superpowers/specs/2026-05-20-agent-bootstrap-cleanup-design.md` 에 저장
- self-review (placeholder·일관성·scope·ambiguity 1회)
- 사용자 spec 리뷰 (필요 시 코멘트 반영)
- `git add` + `git commit -m "docs: add cleanup spec"`

### Step 2. writing-plans 스킬 호출
- 인자: 이 spec 파일 경로 + "agent-bootstrap 코드베이스 cleanup, 6 Phase 단일 spec"
- writing-plans 가 각 Phase 의 항목을 sub-task 단위 plan 으로 변환
- 의존성 그래프 따라 자동 정렬 (B notion.py 단위 테스트가 먼저, A 리팩터, ...)
- 결과: 실행 가능한 sub-task plan (예: 15-25 개)
- 저장 위치: `docs/superpowers/plans/2026-05-20-agent-bootstrap-cleanup.md`

### Step 3. GitHub 라벨·템플릿 사전 준비
- `github-dev:create-issue-label` 호출:
  - phase 라벨: `phase-A`, `phase-B`, `phase-C`, `phase-D`, `phase-E`, `phase-F`
  - type 라벨: `refactor`, `test`, `security`, `docs`, `infra`
  - priority 라벨: `p0-blocker`, `p1-high`, `p2-normal`
- `.github/ISSUE_TEMPLATE/phase-task.md` 생성 (sub-task 표준 양식)
- `.github/PULL_REQUEST_TEMPLATE.md` 생성 (체크리스트: 테스트 추가·CI 통과·spec 항목 매핑)
- (옵션) milestone `agent-bootstrap-cleanup-2026Q2` 생성

### Step 4. `github-dev:decompose-issue`
- writing-plans 의 sub-task plan → GitHub Issues 자동 생성
- 각 이슈에 phase 라벨·type 라벨 부여
- 의존성을 issue body 의 `Blocked by #N` 로 표시
- 이슈 수: 약 15-25 개 (각 phase 당 2-5 개)

### Step 5. 각 이슈를 `github-dev:resolve-issue` 로 처리 (반복)
의존성 순으로 자동 진행. 한 이슈 = 한 PR. cr-fix loop on.

이슈 처리 sequence:
1. 브랜치 생성: `phase-{A-F}/<short-desc>` (예: `phase-A/split-handle-message`)
2. 코드 변경 (작은 surgical diff — 한 이슈 = 한 책임)
3. 단위·통합 테스트 추가 (Phase B 결과물 사용)
4. 로컬 검증: `python -m py_compile` / `bash -n` / `AST parse` / `uv run pytest tests/`
5. 커밋 컨벤션: `refactor:` / `test:` / `feat:` / `docs:` / `chore:`
6. push + PR 생성 (이슈 자동 link: `Closes #N`)
7. PR 안에서 cr-fix loop:
   - 자동 review (또는 사용자 review)
   - 코멘트 받은 fix 자동 반영
   - 재 push
8. CI 통과 (GHA test.yml + lint.yml 모두 green) 확인
9. PR 을 ready for review 로 전환

### Step 6. 사용자 merge
- 머지 방식: **squash merge** (브랜치당 main 에 1 커밋)
- 머지 전 검증:
  - CI 두 워크플로우 green
  - 의존 이슈들 (blocked by) 모두 closed
  - PR 본문 체크리스트 (테스트·spec 매핑) 모두 체크됨

### Step 7. `github-dev:post-merge`
- 머지된 브랜치 로컬·원격 삭제 (`git branch -d` + `git push origin --delete`)
- 학습 사항 반영:
  - 새 패턴 발견 시 `CLAUDE.md` 에 한 줄 추가
  - 모듈별 변화 시 `modules/*.md` 동기화
  - 비목표 였으나 변경된 사항 있으면 spec 파일에 코멘트
- 다음 이슈로 진행 신호 (`github-dev:update-progress` 로 milestone 진행률 sync)

### 분기·머지 정책 (PR settings)

- **main 브랜치 보호**: 직접 push 금지, PR 통해서만 (GitHub Settings → Branches → Protect main)
- **CI 통과 필수**: GHA test.yml + lint.yml 둘 다 green 아니면 머지 불가
- **머지 방식**: squash (브랜치당 1 커밋, 깨끗한 main 히스토리)
- **PR 크기 제한**: 한 PR = 한 sub-task (Phase 보다 작음). 큰 PR 은 reviewer 가 reject 권장
- **draft PR**: 작업 중에는 draft, 완료 시 ready for review

### 의존성 처리 (수동 조정 가능)

writing-plans 가 의존성 따라 자동 정렬하지만 사용자 reorder 가능:
- B notion.py 단위 테스트 (블로커 없음) → 가장 먼저
- A 리팩터 (B 일부 깔린 후 안전) → 두 번째
- C·D·E·F → A·B 위에서 병렬 가능

각 이슈의 `Blocked by` 필드로 GitHub UI 에 표시. blocked 이슈는 resolver 가 자동 skip + 의존 완료 후 재개.

---

## 출처 (Phase 1 Explore 결과)

### 코드 라인 (직접 grep/Read 로 확인 — 1차 수정 반영된 현재 상태)
- `daemon.py:117-140` ENV 로드 + BOT_USER_ID 1차 수정
- `daemon.py:151-159` DISCUSSION_TRIGGER / DISCUSSION_STOP regex
- `daemon.py:161-162` 글로벌 `web`, `sock`
- `daemon.py:165-170` log() 함수 (현재)
- `daemon.py:222` call_claude timeout=900 하드코딩
- `daemon.py:241-242` `_dialog_self_turn_count`, `_discussion_mode` 글로벌
- `daemon.py:259-345` notion_log_turn (87줄)
- `daemon.py:348-496` handle_message (150줄+)
- `daemon.py:499-507` on_event
- `slack-session-summary.sh:24` SLACK_HOOK_RUNNING 가드
- `slack-session-summary.sh:30` export SLACK_HOOK_RUNNING=1
- `slack-session-summary.sh:276` Bot Token 폴백 (1차 수정 후)
- `slack-session-summary.sh:325` chat.postMessage curl
- `notion.py:19` NOTION_VERSION = 2025-09-03
- `notion.py:82-99` mask_secrets
- `notion.py:160` notion_request (retry/backoff)
- `notion.py:288+` upsert_by_external_id

### 문서
- `SKILL.md` B 카테고리 .tmpl 목록, C·D 카테고리 (Windows 검증 + AI 즉석)
- `CLAUDE.md` 1차 수정 후 (105 → 72줄)
- `modules/01-slack-bridge.md` 사전 점검 섹션 (1차 수정 후)
- `modules/04-notion-archive.md` Step 5·6 skip 조건 (1차 수정 후)
- `README.md:11` 보안 경고 (1차 수정 후)
- `README.md:89-90` 버전 핀·비용 추정 (1차 수정 후)
