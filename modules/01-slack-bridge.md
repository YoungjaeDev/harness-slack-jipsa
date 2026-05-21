# 모듈 1: 슬랙 ↔ 클로드 코드 양방향

> AI는 이 문서를 읽고 사용자에게 1:1로 안내합니다. 사용자는 이 문서를 직접 읽지 않습니다.

## 무엇을 깔까

**슬랙 → 클로드 코드**: 슬랙 채널 메시지 → 백그라운드 daemon → `claude --print --resume <session_id>` → 응답을 채널에 post.

**클로드 코드 → 슬랙** (Stop hook): Claude Code 세션 끝나면 → 자동으로 채널에 세션 요약 post.

이 모듈은 운영 환경에서 매일 작동하는 검증된 코드를 그대로 사용합니다. `templates/` 안의 파일을 사용자 환경에 복사하면 됩니다.

---

## 사전 조건

- macOS / Windows / Linux (AI가 분기 처리)
- Claude Code 설치됨
- 슬랙 워크스페이스 (개인 무료 가능)
- Python 3.9+ (macOS 기본 `/usr/bin/python3`, Windows `py -3`, Linux `/usr/bin/python3`)
- **SKILL.md Step 0 보안 확인 3개를 모두 YES로 답한 사용자**. (안 되어 있으면 먼저 SKILL.md로 돌아가서 확인)
- **SKILL.md Step 1.5 설치 스코프 (글로벌 / 프로젝트) 가 결정된 상태**. 결정 안 했으면 SKILL.md 로 돌아가 Step 1.5 진행.

> **인스턴스 표기**: 이 문서는 식별자에 `{INSTANCE}` / `{PROJECT_SUFFIX}` 토큰을 사용합니다.
> - 글로벌: `{INSTANCE}` = `slack-jipsa`, `{PROJECT_SUFFIX}` = (빈 문자열)
> - 프로젝트: `{INSTANCE}` = `slack-jipsa-{PROJECT_ID}`, `{PROJECT_SUFFIX}` = `-{PROJECT_ID}`

### 이미 부분 셋업되어 있는지 사전 점검 (AI)

다음 파일이 이미 존재하면 해당 단계는 skip하세요 (멱등하지만 사용자에게 노이즈). `{INSTANCE}` 는 Step 1.5 에서 정해진 값:
- `~/.claude/scripts/lib/notion.py` 있음 → Step 8의 lib cp skip
- `~/.claude/scripts/{INSTANCE}/daemon.py` 있음 → Step 12 skip
- `~/.claude/hooks/slack-session-summary.sh` 있음 → Step 15의 hook cp skip

존재 확인은 `Test-Path` (Windows) 또는 `ls` (macOS/Linux).

---

## 단계별 안내 (AI가 따라가는 순서)

### Step 1. 슬랙 앱 생성

사용자에게:
```
1) https://api.slack.com/apps 열어주세요
2) "Create New App" → "From scratch" 클릭
3) App Name 입력 (예: "내 비서") + Workspace 선택
4) "Create App" 클릭

완료되면 알려주세요!
```

> **프로젝트 모드 안내** (SKILL.md Step 1.5 에서 "프로젝트별" 선택한 경우): 각 프로젝트는 **별도 Slack App + Channel** 이 필요합니다. Socket Mode 토큰 (`xapp-...`) 을 두 daemon 이 공유하면 메시지 라우팅이 비결정적입니다. 위 단계의 App Name 에 프로젝트명을 포함시키고 (예: "내 비서 — foo"), Step 7 에서 그 프로젝트 전용 채널을 새로 만드세요.

### Step 2. Bot Token Scopes

사용자에게 — 왼쪽 메뉴 "OAuth & Permissions" → "Bot Token Scopes" 에 7개 추가:
```
chat:write
groups:history
groups:read
reactions:write
users:read
files:read
chat:write.public
```

### Step 3. Socket Mode + App-Level Token

왼쪽 메뉴 "Socket Mode" → ON → Token Name `socket-mode` + Scope `connections:write` → Generate → **xapp-... 토큰 사용자가 임시 저장**.

### Step 4. Event Subscriptions

"Event Subscriptions" → ON → "Subscribe to bot events" 에 `message.groups` 추가 → Save.

### Step 5. App Home

"App Home" → Display Name 설정 + "Messages Tab" ON + "Allow users to send messages" 체크.

### Step 6. Install App + Bot Token

"Install App" → "Install to Workspace" → 허용 → **xoxb-... 토큰 사용자가 임시 저장**.

### Step 7. 슬랙 채널 + 봇 초대 + ID 수집

사용자에게:
```
1) 새 비공개 채널 만들기 (글로벌이면 #내-비서, 프로젝트 모드면 #프로젝트명-비서)
2) 채널 ⚙️ → Integrations → Add an App → 만든 봇 추가
3) 채널 이름 우클릭 → View channel details → 맨 아래 Channel ID 복사
4) 본인 프로필 → ⋯ → Copy member ID 복사
```

사용자한테 채널 ID (C0...) 와 본인 user ID (U0...) 받기.

> 프로젝트 모드면 글로벌 daemon 이 쓰는 채널과 **다른** 채널이어야 합니다. 같은 채널을 두 daemon 이 듣고 있으면 메시지가 중복 응답됩니다.

### Step 8. AI 작업 — 폴더 + lib 의존성 카피

검증 코드는 `~/.claude/scripts/lib/` 의 helper 모듈을 사용합니다. 키트의 검증된 lib를 사용자 환경에 복사:

```bash
# {INSTANCE} = 글로벌이면 "slack-jipsa", 프로젝트면 "slack-jipsa-{PROJECT_ID}"
mkdir -p ~/.claude/secrets ~/.claude/scripts/lib ~/.claude/scripts/{INSTANCE}/{logs,sessions} ~/.claude/hooks
touch ~/.claude/scripts/lib/__init__.py

# lib 카피 (절대 변경 금지 — 검증된 코드)
cp templates/lib/notion.py ~/.claude/scripts/lib/
cp templates/lib/slack_mrkdwn.py ~/.claude/scripts/lib/
cp templates/lib/md_to_notion.py ~/.claude/hooks/
```

### Step 9. AI 작업 — 시크릿 파일 작성

`.env.example` 을 base로 사용자 토큰 채워서 `~/.claude/secrets/{INSTANCE}.env` 에 Write (글로벌이면 `slack-jipsa.env`, 프로젝트면 `slack-jipsa-{PROJECT_ID}.env`):

```env
SLACK_BOT_TOKEN=xoxb-...        # Step 6에서 받음
SLACK_APP_TOKEN=xapp-...        # Step 3에서 받음
SLACK_CHANNEL=C0...             # Step 7에서 받음
USER_SLACK_ID=U0...             # Step 7에서 받음 (본인)
BOT_USER_ID=                    # Step 11에서 자동 채움
USER_NAME=                      # 사용자에게 본인 호칭 묻기 (예: 철수, 영희)
SLACK_BOT_NAME=                 # 봇 이름 묻기 (예: 내 비서, 집사)
SLACK_SESSION_WEBHOOK=          # 선택, Incoming Webhook URL 있으면
NOTION_API_TOKEN=               # 모듈 4 진행 시 채움
NOTION_SESSION_DB=              # 모듈 4 진행 시 채움
NOTION_DAILY_DB=                # 모듈 4 옵션
PROJECT_ID=                     # 프로젝트 모드면 채움 (글로벌이면 공란)
PROJECT_DIR=                    # 프로젝트 모드면 절대경로 채움 (글로벌이면 공란)
```

권한:
```bash
chmod 600 ~/.claude/secrets/{INSTANCE}.env
```

### Step 10. AI 작업 — slack_sdk 설치

```bash
/usr/bin/pip3 install --user slack_sdk
```

실패 시 venv:
```bash
python3 -m venv ~/.claude/scripts/slack-jipsa/venv
~/.claude/scripts/slack-jipsa/venv/bin/pip install slack_sdk
```

> venv를 쓴 경우, Step 13의 `run.sh` 마지막 줄 `/usr/bin/python3` 부분을 `~/.claude/scripts/slack-jipsa/venv/bin/python` 으로 바꿔야 합니다 (AI가 자동 처리).

### Step 11. AI 작업 — Bot user ID 자동 조회

```bash
set -a; source ~/.claude/secrets/{INSTANCE}.env; set +a
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" https://slack.com/api/auth.test | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('user_id',''))"
```

결과를 `BOT_USER_ID` 에 채워 다시 Write.

### Step 12. AI 작업 — daemon 패키지 그대로 카피

daemon 은 단일 파일이 아니라 디렉토리 (`daemon.py` + 협업 모듈들). 폴더 통째 카피:

```bash
cp -r templates/scripts/slack-jipsa/. ~/.claude/scripts/{INSTANCE}/
```

**수정 불필요** — 인스턴스 분리는 `SLACK_JIPSA_INSTANCE` 환경변수와 `.env` 의 `PROJECT_ID` / `PROJECT_DIR` 만으로 동작. `.env` 만 올바르면 그대로 작동.

### Step 13. AI 작업 — run.sh + 자동 시작 등록

`~/.claude/scripts/{INSTANCE}/run.sh`:
```bash
#!/bin/bash
set -euo pipefail
# SLACK_JIPSA_INSTANCE 가 환경에서 안 주어졌으면 .env 의 PROJECT_ID 로 계산.
export SLACK_JIPSA_INSTANCE="${SLACK_JIPSA_INSTANCE:-{INSTANCE}}"
set -a
source "$HOME/.claude/secrets/${SLACK_JIPSA_INSTANCE}.env"
set +a
exec /usr/bin/python3 "$HOME/.claude/scripts/${SLACK_JIPSA_INSTANCE}/daemon.py"
```
```bash
chmod +x ~/.claude/scripts/{INSTANCE}/run.sh
```

`templates/launchd-daemon.plist.tmpl` 읽고 다음 4개 플레이스홀더 치환 후 `~/Library/LaunchAgents/com.{USERNAME}.{INSTANCE}.plist` 에 Write:
- `{USERNAME}` = `whoami`
- `{HOME}` = `$HOME`
- `{INSTANCE}` = 글로벌이면 `slack-jipsa`, 프로젝트면 `slack-jipsa-{PROJECT_ID}`
- `{PROJECT_SUFFIX}` = 글로벌이면 빈 문자열, 프로젝트면 `-{PROJECT_ID}`

```bash
launchctl load ~/Library/LaunchAgents/com.{USERNAME}.{INSTANCE}.plist
launchctl list | grep slack-jipsa
```

PID 가 보이면 정상. 글로벌과 프로젝트 인스턴스가 공존하는 경우 위 grep 에 두 행이 보입니다.

### Step 14. 검증 1 — 슬랙 → 클코

사용자에게:
```
방금 만든 슬랙 채널에서 "안녕" 보내주세요.
5~30초 안에:
1) 봇이 ⏳ reaction
2) 응답 post
3) ✅ reaction

됐나요?
```

안 되면:
```bash
tail -30 ~/.claude/scripts/{INSTANCE}/logs/$(date +%Y-%m-%d).log
```

### Step 15. AI 작업 — Stop hook 셋업 (클코→슬랙)

이게 양방향의 핵심. 어떤 Claude Code 세션이든 끝나면 자동으로 슬랙에 보고.

```bash
cp templates/hooks/slack-session-summary.sh ~/.claude/hooks/
cp templates/hooks/append_turn_raw.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/slack-session-summary.sh
```

`~/.claude/settings.json` Read → `hooks.Stop` 배열에만 append (기존 배열·키 보존):

```json
{
  "hooks": {
    "Stop": [
      { "type": "command", "command": "$HOME/.claude/hooks/slack-session-summary.sh" }
    ]
  }
}
```

> **env 섹션 작성 불필요** — Stop hook 이 `.env` 를 직접 읽으므로, 이미 채워둔 토큰이 그대로 사용됩니다. settings.json `env` 에 같은 토큰을 중복 작성하지 마세요 (drift 위험).
>
> Stop hook 의 .env 선택:
> 1. **프로젝트 모드**: stdin JSON 의 `cwd` 를 `~/.claude/scripts/slack-jipsa-shared/projects.json` 의 등록 경로와 prefix match → 가장 긴 path 의 `id` → `~/.claude/secrets/slack-jipsa-{id}.env`. (Step 15.5 에서 등록.)
> 2. 매치 실패 시: 글로벌 fallback `~/.claude/secrets/slack-jipsa.env`. (기존 사용자 호환 보장.)
>
> Stop hook 의 슬랙 전송 경로:
> 1. `.env` 의 `SLACK_SESSION_WEBHOOK` 가 있으면 webhook 으로 (별도 채널/포맷 분리할 때)
> 2. 없으면 `.env` 의 `SLACK_BOT_TOKEN` + `SLACK_CHANNEL` 로 자동 폴백 (모듈 1 완료 시 이미 채워져 있음 — 추가 작업 불필요)
>
> 노션 적재는 `.env` 의 `NOTION_API_TOKEN` + `NOTION_SESSION_DB` 가 채워지면 자동 (모듈 4 진행 후).

#### Incoming Webhook (선택)

분리된 채널/포맷으로 받고 싶을 때만. 모듈 1 완료만으로도 Bot Token 폴백으로 슬랙 보고가 옵니다. 굳이 만들 필요 없음.

### Step 15.5. AI 작업 — projects.json upsert (프로젝트 모드 한정)

> 글로벌 모드면 이 단계 통째 skip. Step 16 으로.

Stop hook 이 헤드리스 세션의 cwd 를 어느 인스턴스로 라우팅할지 알려면 cwd ↔ id 매핑 파일이 필요합니다. 위치:

```text
~/.claude/scripts/slack-jipsa-shared/projects.json
```

스키마:
```json
{
  "version": 1,
  "projects": [
    {"path": "C:/dev/harness-slack-jipsa", "id": "harness-slack-jipsa"}
  ]
}
```

AI 가 처리 — 이미 같은 `path` 가 있으면 `id` 덮어쓰기, 없으면 append. atomic write (tmp → rename) 만 보장. 사용자에게 직접 손대게 하지 말 것.

작업 흐름:
1. `~/.claude/scripts/slack-jipsa-shared/` 가 없으면 `mkdir -p`
2. 기존 `projects.json` 이 있으면 Read 해서 `projects` 배열에 upsert, 없으면 새로 생성
3. `path` 는 사용자가 Step 1.5 (b) 에서 답한 절대경로 (Windows 면 `\` 를 `/` 로 정규화해 저장 권장 — Stop hook 매칭 시 둘 다 처리)
4. `id` 는 Step 1.5 (b) 의 확정 `PROJECT_ID`
5. tmp 파일에 Write 후 `mv` 또는 `Move-Item -Force`

사용자에게 한 번만 고지:
```text
참고: ~/.claude/scripts/slack-jipsa-shared/projects.json 에
이 프로젝트 경로↔ID 매핑을 기록했어요. Stop hook 이 어떤 폴더에서 떨어진 세션을
어느 슬랙 채널로 보낼지 정하는 데 사용됩니다. 이 키트 외부에서 직접 편집하지 마세요.
```

### Step 16. 검증 2 — 클코 → 슬랙

사용자에게:
```
새 터미널에서:
claude --print "1+1은?"

응답 후 슬랙 채널에 세션 보고 메시지 자동으로 오나요?
```

안 되면:
```bash
tail -30 /tmp/slack-session-summary.log
```

webhook 안 만들었으면 슬랙엔 안 옴. 노션 적재 (모듈 4) 진행 후 노션에 row 생기는지로 검증.

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| `dispatch_failed` | Step 2 권한 누락 (`groups:history`). Install App 다시. |
| 봇 응답 없음 | `launchctl list \| grep slack-jipsa` PID 확인 (글로벌·프로젝트 둘 다 표시) |
| `ModuleNotFoundError: lib.notion` | Step 8 lib 카피 누락. `ls ~/.claude/scripts/lib/notion.py` |
| `Permission denied` (.env) | `chmod 600 ~/.claude/secrets/{INSTANCE}.env` |
| Stop hook 발동 안 함 | `~/.claude/settings.json` hooks.Stop 등록 확인 |

---

## OS별 분기 — Windows

위 단계의 macOS/Linux 부분을 Windows로 번역하면서 안내. AI 책임 — `templates/scripts/slack-jipsa/daemon.py` (Python 코드, OS 독립) 그대로 사용 가능. 다음만 PowerShell로:

- 폴더 만들기: `New-Item -ItemType Directory -Force -Path`
- 파일 카피: `Copy-Item`
- 시크릿 권한: `icacls ... /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F"`
- daemon 자동 시작: launchd 대신 Task Scheduler (`Register-ScheduledTask`, at logon trigger)
- run.sh 대신 run.ps1 (env 로드 후 daemon.py 실행)
- Stop hook command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ~/.claude/hooks/slack-session-summary.ps1`
- AI 책임: `slack-session-summary.sh` (bash) 를 PowerShell로 번역해서 `slack-session-summary.ps1` 생성. 핵심 로직: stdin JSON 받기 → transcript 추출 → curl 대신 `Invoke-RestMethod` 로 슬랙 + 노션 post

## OS별 분기 — Linux

위 단계의 macOS 부분을 Linux로 번역. 거의 동일 (bash 그대로). 차이점:
- 자동 시작: launchd 대신 systemd user service (`templates/systemd-slack-jipsa.service.tmpl` 참고)
- `loginctl enable-linger $(whoami)` 로 로그아웃 후에도 작동
- 패키지: `apt install python3-pip jq curl` 또는 `dnf install`
