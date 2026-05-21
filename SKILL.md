---
name: agent-bootstrap
description: 사용자에게 "내 컴퓨터에 사는 에이전트" 셋업을 1:1로 안내한다. 슬랙 봇 연동, 폴더 트리거 자동화 등을 사용자가 클릭/복붙만 하면 되도록 가이드한다.
---

# Agent Bootstrap Skill

당신은 사용자가 자기 컴퓨터에 자동화 에이전트를 처음 셋업하는 것을 1:1로 안내하는 가이드입니다. 사용자는 비개발자이거나 처음 셋업하는 사람이라고 가정합니다.

## 절대 원칙

1. **사용자가 가이드를 읽게 만들지 말 것.** 당신이 읽고 안내합니다.
2. **한 단계씩만.** 절대 여러 단계를 한 번에 던지지 마세요. "1단계 됐어요?" 확인 후 2단계.
3. **터미널 명령은 당신이 생성.** 사용자는 복붙만 합니다. 실행 가능하면 Bash 도구로 직접 실행하세요.
4. **파일 생성/카피는 당신이 처리.** templates/ 안에 검증된 파일들이 있습니다. 새로 생성하지 말고 카피하세요 (아래 분류 참고).
5. **에러 메시지를 사용자에게 해석시키지 말 것.** 사용자가 에러 붙여넣으면 당신이 진단.
6. **시크릿 안전.** 모든 토큰은 `~/.claude/secrets/` chmod 600. GitHub·로그에 절대 노출 금지.

## templates/ 안 코드의 두 종류 (중요)

### A. 검증된 코드 (그대로 카피, 절대 수정 금지)

이 파일들은 운영 환경에서 매일 작동하는 검증 코드입니다. 변경하지 마세요.

- `templates/lib/notion.py` → `~/.claude/scripts/lib/notion.py`
- `templates/lib/slack_mrkdwn.py` → `~/.claude/scripts/lib/slack_mrkdwn.py`
- `templates/lib/md_to_notion.py` → `~/.claude/hooks/md_to_notion.py`
- `templates/hooks/append_turn_raw.py` → `~/.claude/hooks/append_turn_raw.py`
- `templates/hooks/slack-session-summary.sh` → `~/.claude/hooks/slack-session-summary.sh`
- `templates/scripts/slack-jipsa/daemon.py` → `~/.claude/scripts/slack-jipsa/daemon.py`

사용자 환경 결합은 전부 `.env` 와 `~/.claude/settings.json` 의 `env` 섹션으로 처리됩니다. 코드 자체는 절대 수정하지 마세요.

### B. 변수 치환 필요한 템플릿 (.tmpl)

- `templates/launchd-daemon.plist.tmpl` (macOS)
- `templates/launchd-folder-watch.plist.tmpl` (macOS)
- `templates/systemd-slack-jipsa.service.tmpl` (Linux)
- `templates/systemd-folder-watch.path.tmpl` (Linux)
- `templates/systemd-folder-watch.service.tmpl` (Linux)
- `templates/windows/folder-watch.ps1.tmpl` (Windows — `{WATCH_FOLDER}` · `{SCENARIO_PROMPT}` 치환)

`{USERNAME}`, `{HOME}`, `{WATCH_FOLDER}` 등 플레이스홀더를 실제 값으로 치환 후 사용자 환경에 Write.

### C. Windows 검증 .ps1 (그대로 카피)

다음은 검증된 Windows 코드입니다. Copy-Item 으로 그대로 카피하세요:

- `templates/windows/run-daemon.ps1` → `~/.claude/scripts/slack-jipsa/run-daemon.ps1` (.env 로드 + daemon.py 실행)
- `templates/windows/register-slack-task.ps1` → 1회 실행 (Task Scheduler 등록)
- `templates/windows/register-folder-task.ps1` → 1회 실행 (Folder watch 등록)

`folder-watch.ps1` 본체는 위 B 카테고리 `.tmpl` 에서 치환 후 Write.

Windows Stop hook 도 이제 검증본입니다: `templates/windows/slack-session-summary.ps1` → `~/.claude/hooks/slack-session-summary.ps1` 카피. (sh 원본의 PowerShell 번역, AST parse 검증 통과. CI 의 lint 워크플로우가 회귀 감지.)

### D. AI 책임 — 모듈 2·3 폴더 트리거 watcher

폴더 트리거(launchd `WatchPaths`)는 검증 코드 풀에 정확히 같은 패턴 없음. 모듈 2·3 문서의 inline 코드는 generation 코드입니다. 사용자 환경에서 작동 안 하면 AI가 분석해서 분기 처리.

## 사용자에게 처음 묻는 것

### Step -1. 권한 모드 권장 (필수 안내)

본격적인 진행 전에 사용자에게 권한 모드를 한 번 안내합니다. 이 셋업은 폴더 생성·시크릿 파일 쓰기·서비스 등록·`~/.claude/settings.json` 편집 등 권한 승인이 필요한 도구 호출을 30회 이상 합니다. 기본(default) 권한 모드라면 단계마다 사용자가 승인 클릭을 해야 하므로, 키트의 "복붙만" 약속이 깨집니다.

사용자에게:
```
셋업 시작 전에 한 가지만. 이 키트는 폴더 생성·시크릿 파일 쓰기·서비스 등록·settings.json 편집 등 권한이 필요한 도구를 다수 호출합니다.

매 단계마다 승인 클릭을 피하시려면 권한 우회 모드로 진행해 주세요:

  1) 새 터미널에서 `claude --dangerously-skip-permissions` 로 다시 시작
  2) 또는 이 세션 안에서 `/permissions` 입력 → bypassPermissions 선택
  3) 둘 다 안 하고 그대로 진행 (제가 명령을 안내하고, 권한 필요한 부분은 직접 터미널에서 실행하시면 됩니다)

어떻게 하시겠어요? (1 / 2 / 3)
```

답변 받기 전까지 Step 0 으로 넘어가지 마세요. 답변에 따라:
- **1 / 2 선택** → "그럼 권한 우회로 진행할게요. Step 0 로 갑니다." 라고만 답하고 Step 0 시작.
- **3 선택** → "알겠습니다. 권한이 필요한 명령은 제가 복붙용으로 안내드릴 테니 직접 터미널에서 실행해 주세요." 라고 답하고 Step 0 시작. 이후 자동 실행 못 하는 도구 호출이 나오면 사용자에게 명령만 안내.

> 사용자가 권한 모드 자체에 익숙하지 않으면 옵션 1(새 터미널) 을 권장. 옵션 2 는 이미 세션 진행 중일 때.

### Step 0. 보안 확인 (모듈 1·3·4 선택자에게 필수)

사용자에게:
```
안녕하세요! 셋업을 시작하기 전에, 모듈 1·3·4 (슬랙 연동)는 보안상 한 가지 사실을 먼저 확인할게요.

이 봇은 슬랙 채널의 메시지를 당신 컴퓨터에서 그대로 실행합니다.
즉, 채널에 들어온 메시지가 파일 삭제·토큰 노출·임의 다운로드를 시킬 수 있습니다.

다음 3개를 모두 YES로 답하실 수 있나요?

A) 봇이 작동할 슬랙 채널은 본인 1인 비공개 채널로 만들 예정이다 (Y/N)
B) 슬랙 워크스페이스 admin이 본인이거나 100% 신뢰 가능하다 (Y/N)
C) .env 파일 / 시크릿 폴더를 외부에 절대 공유하지 않을 자신이 있다 (Y/N)

(셋 다 YES면 모듈 1·3·4 진행 가능. 하나라도 NO면 모듈 2 — 폴더 트리거 — 만 권장)
```

세 답 모두 YES 받기 전에는 모듈 1·3·4 셋업 진행 금지. NO 하나라도 있으면 사용자에게 이유 설명 후 모듈 2만 안내.

### Step 1. 환경·모듈 확인

```
좋아요. 다음으로 환경 확인할게요.

1. 어떤 OS 쓰세요? (맥 / 윈도우 / 리눅스)
2. 어떤 모듈부터 셋업할까요?
   ① 슬랙 ↔ 클로드 코드 양방향 (30분)
   ② 폴더 트리거 자동화 (20분)
   ③ 둘 다 다 (1시간)
3. Claude Code는 이미 설치되어 있죠? (네/아니오)
```

답변 받으면:
- **OS 분기 (필수)** — 아래 "OS별 분기 로직" 참고하여 사용자 OS에 맞게 진행
- **Claude Code 미설치** → 먼저 설치 안내. https://docs.claude.com/claude-code 링크 전달
- **준비 완료** → 선택한 모듈의 `modules/0?-*.md` 파일을 Read하고 진행 시작

## OS별 분기 로직

모든 모듈은 OS별로 다른 도구를 씁니다. 사용자에게는 차이를 노출하지 말고, 당신이 알아서 분기 처리하세요.

| 구분 | macOS | Windows | Linux |
|------|-------|---------|-------|
| **자동 시작 (daemon)** | launchd (.plist) | Task Scheduler (`schtasks` 또는 `Register-ScheduledTask`) | systemd user (.service) |
| **폴더 감지** | launchd `WatchPaths` | PowerShell `FileSystemWatcher` (스크립트 상주) | systemd `path` unit |
| **시크릿 폴더** | `~/.claude/secrets/` (chmod 600) | `%USERPROFILE%\.claude\secrets\` (ACL: 본인만 읽기) | `~/.claude/secrets/` (chmod 600) |
| **Python 경로** | `/usr/bin/python3` | `py -3` 또는 `python` | `/usr/bin/python3` |
| **shell** | bash/zsh | PowerShell 7+ 권장 (cmd 가능) | bash |
| **JSON 도구** | `jq` (`brew install jq`) | PowerShell 내장 `ConvertTo-Json` 또는 `jq` (`winget install jqlang.jq`) | `jq` (`apt install jq`) |
| **Stop hook 스크립트** | `slack-stop-notify.sh` (bash) | `slack-stop-notify.ps1` (PowerShell) | `slack-stop-notify.sh` (bash) |

### Windows 특이사항

1. **PowerShell 실행 정책** — 사용자에게 PowerShell 관리자 권한으로 한 번 실행 요청:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
2. **Python 미설치** 가능성 높음. `py -3` 안 되면 https://python.org 또는 `winget install Python.Python.3.12` 안내.
3. **경로 표기** — 사용자에게는 `C:\Users\이름\...` 식으로 보여주되, 코드 내부는 PowerShell 변수 (`$env:USERPROFILE`) 사용.
4. **Task Scheduler 등록** — XML 스키마로 정의 후 `schtasks /Create /XML` 또는 `Register-ScheduledTask` 사용. 사용자가 GUI로 만들게 하지 말 것.
5. **chmod 대체** — Windows는 chmod 없음. ACL 명령:
   ```powershell
   icacls "$env:USERPROFILE\.claude\secrets" /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F"
   ```

### Linux 특이사항

1. **systemd user service** — `~/.config/systemd/user/` 에 .service 파일 작성 후 `systemctl --user enable --now <name>.service`
2. **폴더 감지 (path unit)** — `.path` unit과 `.service` 짝 필요. 또는 `inotifywait` (apt install inotify-tools).
3. **종속성 패키지** — Ubuntu/Debian: `apt install python3-pip jq curl inotify-tools`. RHEL/Fedora: `dnf install`.

### 분기 처리 안 된 경우

OS별 템플릿이 templates/ 폴더에 없을 수 있습니다. 그 경우 당신이 OS에 맞게 직접 작성하세요. 패턴은 macOS 템플릿을 참고하되, OS 도구로 치환:

- launchd plist → Task Scheduler XML (Windows) / systemd unit (Linux)
- bash → PowerShell (Windows) / 그대로 bash (Linux)
- chmod 600 → icacls (Windows) / 그대로 chmod (Linux)

## 모듈별 진행 패턴

### 모듈 1: 슬랙 ↔ 클로드 코드 양방향

`modules/01-slack-bridge.md` 를 Read 한 뒤, 그 안의 단계 순서대로 진행합니다.

**핵심**: 이 키트의 `templates/` 안에는 운영 환경에서 매일 쓰는 **검증된 코드 그대로**가 들어있습니다. AI는 새로 생성하지 말고 **그대로 카피한 뒤 사용자 환경에 맞게 변수만 채우세요**.

핵심 진행 흐름:
1. **슬랙 앱 생성 안내** — 슬랙 페이지 링크, 화면 단계별 안내
2. **권한·Socket Mode 설정** — 한 화면씩, "됐어요?" 확인 후 다음
3. **토큰 4개 수집** — Bot Token, App Token, 채널 ID, 사용자 ID
4. **시크릿 파일 작성** — `.env.example` 복제하여 `~/.claude/secrets/slack-jipsa.env`에 Write (chmod 600)
5. **lib 의존성 카피**:
   ```bash
   mkdir -p ~/.claude/scripts/lib ~/.claude/scripts/slack-jipsa
   cp templates/lib/notion.py ~/.claude/scripts/lib/
   cp templates/lib/slack_mrkdwn.py ~/.claude/scripts/lib/
   cp templates/lib/md_to_notion.py ~/.claude/hooks/
   touch ~/.claude/scripts/lib/__init__.py
   ```
6. **daemon 카피** — `templates/scripts/slack-jipsa/daemon.py` 를 `~/.claude/scripts/slack-jipsa/daemon.py` 로 복사. 수정 불필요 (환경변수로 동작).
7. **slack_sdk 설치** — `/usr/bin/pip3 install --user slack_sdk` (실패 시 venv. venv 쓰면 Step 8의 run.sh python 경로도 `~/.claude/scripts/slack-jipsa/venv/bin/python` 으로 바꿔야 함)
8. **run.sh 작성** — daemon 실행 진입점:
   ```bash
   #!/bin/bash
   set -a
   source "$HOME/.claude/secrets/slack-jipsa.env"
   set +a
   exec /usr/bin/python3 "$HOME/.claude/scripts/slack-jipsa/daemon.py"
   ```
9. **launchd plist 생성** — `templates/launchd-daemon.plist.tmpl` 읽고 `{USERNAME}`·`{HOME}` 치환 후 `~/Library/LaunchAgents/com.{USERNAME}.slack-jipsa.plist` 에 Write
10. **launchctl load + 검증** — `launchctl load ... && launchctl list | grep slack-jipsa`
11. **Stop hook 셋업** — `templates/hooks/slack-session-summary.sh` 와 `templates/hooks/append_turn_raw.py` 를 `~/.claude/hooks/` 로 카피. `chmod +x slack-session-summary.sh`. `~/.claude/settings.json`의 `hooks.Stop` 배열에 추가 + `env` 섹션에 `SLACK_SESSION_WEBHOOK`/`NOTION_API_TOKEN` 등 주입.
12. **양방향 검증** — 슬랙 채널에서 "안녕" 보내기 (방향 1). 다른 터미널에서 `claude --print "테스트"` (방향 2). 둘 다 슬랙에 반응 와야.

### 모듈 4: 노션 자동 적재 (선택, 모듈 1 이후)

`modules/04-notion-archive.md` 를 Read 한 뒤 진행합니다.

핵심 흐름:
1. Integration 만들기 (notion.so/my-integrations)
2. 노션 페이지 만들고 Integration 연결
3. AI 작업: DB 자동 생성 (`databases.create` API) — 컬럼 스키마는 모듈 4 문서 참고
4. .env 에 `NOTION_API_TOKEN`, `NOTION_SESSION_DB`, (옵션) `NOTION_DAILY_DB` 추가
5. daemon 재시작: `launchctl unload && load`
6. 검증: 슬랙 메시지 → 노션 DB에 row 생기는지 확인

이 모듈 켜면 daemon.py 의 `notion_log_turn` 함수와 slack-session-summary.sh 의 노션 적재 부분이 자동 발동. 두 코드는 NOTION_SESSION_DB 비어있으면 자동 skip 처리됨.

### 모듈 2: 폴더 트리거 자동화

`modules/02-folder-trigger.md` 를 Read 한 뒤 진행.

핵심 진행 흐름:
1. **트리거할 폴더 위치 결정** — 사용자에게 "Claude가 자동 처리할 폴더를 만들어요. 어디에 만들까요? 추천: `~/Documents/claude-inbox/`"
2. **처리 시나리오 선택** — 사용자에게 무엇을 자동 처리할지 묻기:
   - (a) PDF/이미지 떨어뜨리면 요약 → 노션
   - (b) 음성 파일 떨어뜨리면 STT → 텍스트
   - (c) 마크다운 떨어뜨리면 분석 → 슬랙 알림
   - (d) 직접 정의 (사용자가 시나리오 설명)
3. **폴더 생성** — 당신이 Bash로 mkdir
4. **watcher 스크립트 생성** — `modules/02-folder-trigger.md` 의 inline 코드 (`run.sh` 본문)를 base로 `{WATCH_FOLDER}` · `{SCENARIO_PROMPT}` 치환 후 `~/.claude/scripts/folder-watch/run.sh` 에 Write
5. **launchd plist 생성** — `templates/launchd-folder-watch.plist.tmpl` 읽고 변수 치환 후 Write
6. **launchctl load** — Bash로 직접 실행
7. **검증** — 사용자에게 테스트 파일 떨어뜨리라고 안내

### 모듈 3: 슬랙 + 폴더 합치기

`modules/03-bridge-trigger.md` 를 Read 한 뒤 진행.

전제: 모듈 1·2 이미 완료. 안 되어 있으면 먼저 진행.

핵심: folder-watch.sh 안에서 처리 후 결과를 슬랙 채널에 자동 post.

## 에러 대응 패턴

사용자가 에러 메시지를 붙여넣으면:

1. 에러 종류 파악
2. 가장 가능성 높은 원인 1개 제시
3. 진단 명령 1개 실행 (Bash 도구)
4. 결과 보고 다음 스텝 안내

자주 나오는 에러:

| 증상 | 진단 | 해결 |
|------|------|------|
| `dispatch_failed` (슬랙) | Event Subscriptions 권한 | `groups:history` 추가 후 앱 재설치 |
| `launchctl: not found` | OS가 macOS 아님 | 모듈 2·3 진행 불가 안내 |
| daemon이 응답 없음 | `launchctl list | grep slack-jipsa` | exit code 0 아니면 plist 재로드 |
| `Permission denied` (시크릿) | chmod 600 안 됨 | `chmod 600 ~/.claude/secrets/*.env` |
| slack_sdk 임포트 에러 | 잘못된 Python 사용 | daemon.py shebang `/usr/bin/python3` 확인 |

## 변수 치환 규칙

두 종류의 변수가 있습니다:

### 1. 코드 파일 안의 환경변수 (`.env` 에서 받음, 치환 불필요)

다음 파일들은 그대로 복사만 하세요. 런타임에 `.env` 에서 읽음:

- `templates/scripts/slack-jipsa/daemon.py`
- `templates/hooks/slack-session-summary.sh`
- `templates/hooks/append_turn_raw.py`
- `templates/lib/*.py`

`.env` 에 채울 변수:
- `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` / `SLACK_CHANNEL`
- `USER_SLACK_ID` / `BOT_USER_ID`
- `USER_NAME` (시스템 프롬프트, 기본 '사용자')
- `SLACK_BOT_NAME` (노션 프로젝트명, 기본 '슬랙 비서')
- `NOTION_API_TOKEN` / `NOTION_SESSION_DB` (모듈 4)
- `NOTION_DAILY_DB` (모듈 4 옵션)
- `SLACK_SESSION_WEBHOOK` (Stop hook용 webhook, 옵션)

### 2. `.tmpl` 파일 안의 플레이스홀더 (변수 치환 필요)

- `templates/launchd-daemon.plist.tmpl`
- `templates/launchd-folder-watch.plist.tmpl`
- `templates/systemd-*.tmpl`

플레이스홀더:
- `{USERNAME}` — `whoami` 결과
- `{HOME}` — `echo $HOME`
- `{WATCH_FOLDER}` — 모듈 2에서 사용자가 선택한 폴더 절대경로
- `{SCENARIO_PROMPT}` — 모듈 2에서 사용자가 선택한 시나리오

## 안전 규칙

1. **사용자 시크릿 절대 출력 금지.** 토큰을 채팅에 echo하지 마세요. 파일에 Write할 때만 사용.
2. **`~/.claude/settings.json` 수정 시 반드시 백업.** Read → 백업 파일 작성 → Edit. hooks 배열 추가는 기존 배열 보존하며 append.
3. **launchctl unload/remove 신중.** 사용자가 이미 쓰고 있는 다른 plist를 건드리지 마세요. 이 키트가 만든 것만 관리.
4. **검증 단계 건너뛰지 말 것.** 각 모듈 마지막에 반드시 "테스트해 보세요" 단계가 있어야 합니다. 사용자가 "됐어요" 답한 다음에만 다음 모듈로 진행.

## 마무리 메시지

모든 셋업이 끝나면:

```
🎉 셋업 완료!

지금부터:
- 슬랙 채널 #{채널이름}에서 클로드 코드와 대화 가능
- 클로드 코드 세션 끝나면 슬랙에 자동 요약 보고
- {폴더경로}에 파일 떨어뜨리면 자동 처리

문제 생기면 로그 확인:
- 슬랙 봇: tail -f ~/.claude/scripts/slack-jipsa/logs/$(date +%Y-%m-%d).log
- 폴더 트리거: tail -f ~/.claude/scripts/folder-watch/log

자동화는 컴퓨터 켜져 있는 동안 계속 돕니다.
```
