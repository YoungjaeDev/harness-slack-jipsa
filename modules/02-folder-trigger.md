# 모듈 2: 폴더 트리거 자동화

> AI가 이 문서를 읽고 사용자에게 1:1로 안내합니다.

## 무엇을 깔까

특정 폴더에 파일을 떨어뜨리면 launchd가 변화를 감지 → shell script가 Claude Code를 호출 → 사용자가 정의한 시나리오 실행.

**예시 시나리오**:
- 📄 PDF를 떨어뜨리면 → 자동 요약 → 노션 저장
- 🎤 음성 파일을 떨어뜨리면 → STT → 텍스트 변환
- 📝 마크다운을 떨어뜨리면 → 핵심 추출 → 슬랙 알림
- 🖼️ 이미지를 떨어뜨리면 → 텍스트 추출 → 정리

---

## 사전 조건

- macOS / Windows / Linux 모두 지원 (AI가 분기 처리)
- Claude Code 설치됨
- (선택) 슬랙 알림 원하면 모듈 1 먼저 셋업

---

## 단계별 안내

### Step 1. 폴더 위치 결정

사용자에게:
```
Claude가 자동 처리할 "받은편지함" 같은 폴더를 만들 거예요.
어디에 만들까요?

추천: ~/Documents/claude-inbox/
다른 위치 원하시면 절대경로로 알려주세요.
```

답변 받으면 `{WATCH_FOLDER}` 변수에 저장.

#### 한글/공백 검사 (AI 책임)

답변 경로에 한글 또는 공백이 섞여 있는지 정규식 `[^\x20-\x7e]` 또는 공백으로 검사. 발견 시 사용자에게 한 번만 안내 (진행은 계속):

```text
감지: 선택하신 폴더 경로에 한글 또는 공백이 포함되어 있어요 ({실제 경로}).
진행 자체는 가능하지만, PowerShell 명령에서 quoting 이슈가 생기기 쉬워
더 신중히 진행할게요. 이후 단계에서 명령이 실패하면 quoting 문제일
가능성이 높으니 알려주세요.
```

이후 모든 watcher / launchd / Task Scheduler 명령 생성 시 [SKILL.md Step 1.1](../SKILL.md) 의 PowerShell quoting 규칙 (큰따옴표, call operator, `-LiteralPath`, here-string, `--%`) 을 보수적으로 적용. 특히 Windows `folder-watch.ps1` 의 `claude --print` 호출은 항상 `"$WatchDir"`, `"$prompt"`, `"$log"` 로 모든 변수를 quote.

### Step 2. 처리 시나리오 선택

사용자에게:
```
어떤 자동 처리를 만들까요?

① 📄 PDF/이미지 → 요약 → 같은 폴더에 .summary.md 저장
② 🎤 음성 (.m4a, .mp3) → 텍스트 변환 → .txt 저장
③ 📝 마크다운 (.md) → 핵심 추출 → 슬랙 알림 (모듈 1 필요)
④ 직접 정의 — 어떤 처리를 원하시는지 자유롭게 설명해주세요

번호나 직접 설명을 알려주세요.
```

답변 받으면 `{SCENARIO_PROMPT}` 변수에 저장 (Claude에게 보낼 시스템 프롬프트).

### Step 3. AI 작업 — 폴더 + 인프라 생성

```bash
mkdir -p {WATCH_FOLDER}
mkdir -p {WATCH_FOLDER}/.processed
mkdir -p ~/.claude/scripts/folder-watch/{logs,locks}
```

`.processed/` 는 이미 처리한 파일 이동 위치. 무한 루프 방지.

### Step 4. AI 작업 — watcher 스크립트 생성

아래 inline 코드를 base로 `{WATCH_FOLDER}` · `{SCENARIO_PROMPT}` 치환 후 `~/.claude/scripts/folder-watch/run.sh` 에 Write.

핵심 로직:
```bash
#!/bin/bash
WATCH_DIR="{WATCH_FOLDER}"
PROCESSED_DIR="$WATCH_DIR/.processed"
LOG="$HOME/.claude/scripts/folder-watch/logs/$(date +%Y-%m-%d).log"

# 새 파일 1개씩 처리 (.processed 안 거 + 숨김 파일 제외)
find "$WATCH_DIR" -maxdepth 1 -type f ! -name '.*' | while read -r FILE; do
    BASENAME=$(basename "$FILE")
    echo "[$(date '+%H:%M:%S')] Processing: $BASENAME" >> "$LOG"

    # Claude Code 호출
    PROMPT="{SCENARIO_PROMPT}"
    claude --print --add-dir "$WATCH_DIR" "$PROMPT $FILE" >> "$LOG" 2>&1

    # 처리 완료 → .processed 로 이동
    mv "$FILE" "$PROCESSED_DIR/$(date +%Y%m%d-%H%M%S)-$BASENAME"
done
```

```bash
chmod +x ~/.claude/scripts/folder-watch/run.sh
```

### Step 5. AI 작업 — launchd plist 생성

`templates/launchd-folder-watch.plist.tmpl` 읽어서 변수 치환 후 `~/Library/LaunchAgents/com.{USERNAME}.folder-watch.plist` 에 Write.

핵심 차이: 슬랙 daemon은 `KeepAlive` (계속 살아있음). 폴더 watch는 `WatchPaths` (변화 감지 시만 실행).

```xml
<key>WatchPaths</key>
<array>
    <string>{WATCH_FOLDER}</string>
</array>
<key>ThrottleInterval</key>
<integer>5</integer>
```

`ThrottleInterval` 5초 = 같은 폴더 5초 안에 여러 파일 떨어져도 1번만 실행 (배치 처리).

```bash
launchctl load ~/Library/LaunchAgents/com.{USERNAME}.folder-watch.plist
launchctl list | grep folder-watch
```

### Step 6. 검증

사용자에게:
```
테스트할게요!

방금 만든 폴더 ({WATCH_FOLDER})에 처리할 파일 하나를 떨어뜨려 주세요.
(예: PDF 시나리오면 PDF 파일, 음성 시나리오면 .m4a 파일)

5~30초 안에:
1) 파일이 .processed/ 폴더로 이동
2) 결과 파일이 같은 폴더에 생성 (예: .summary.md) 또는 슬랙 알림

확인되면 알려주세요. 안 되면:

tail -30 ~/.claude/scripts/folder-watch/logs/$(date +%Y-%m-%d).log
```

---

## 시나리오별 SCENARIO_PROMPT 예시

### 시나리오 ①: PDF/이미지 → 요약

```
이 파일을 분석해서 핵심을 3~5문장으로 요약한 후, 같은 폴더에 동일한 이름의 .summary.md 파일로 저장해줘. 파일 경로:
```

### 시나리오 ②: 음성 → STT

전제: **Whisper** 또는 다른 STT 도구가 시스템에 설치되어 있어야 합니다 (macOS 내장 `say`는 TTS이지 STT가 아니므로 사용 불가). 사용자에게 STT 도구 설치 여부 먼저 묻기:
- `whisper --help` 동작 → 그대로 진행
- 미설치 → `pip install openai-whisper` (FFmpeg 사전 설치 필요) 또는 시나리오 ①/③ 권장

```
이 음성 파일을 텍스트로 변환해줘. whisper CLI (또는 openai-whisper Python 패키지) 를 활용하고, 결과를 같은 이름의 .txt로 저장. 음성 파일:
```

### 시나리오 ③: 마크다운 → 슬랙 알림

전제: 모듈 1 완료. 슬랙 봇 토큰 사용 가능.

```
이 마크다운 파일의 핵심을 1~2문장으로 요약하고, 슬랙 채널 {SLACK_CHANNEL}에 post해줘. ~/.claude/secrets/slack-jipsa.env 의 SLACK_BOT_TOKEN을 사용. 파일:
```

### 시나리오 ④: 사용자 정의

사용자가 자유롭게 설명한 내용을 그대로 또는 정제해서 SCENARIO_PROMPT에 사용.

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| 파일 떨어뜨려도 반응 없음 | `launchctl list | grep folder-watch` 확인. plist 재로드. |
| Claude가 파일을 못 읽음 | `--add-dir` 플래그 빠졌나 확인. 파일 절대경로 확인. |
| 같은 파일 반복 처리 | `.processed/` 폴더 이동 로직 확인. 권한 문제일 수 있음. |
| launchd가 너무 자주 실행 | `ThrottleInterval` 늘리기 (5 → 30). |
| `command not found: claude` | shell PATH 문제. plist에 `EnvironmentVariables` 추가하여 PATH 명시. |

---

## 안전 규칙

- 폴더에 **실수로 떨어뜨린 파일은 .processed/에 영구 보존**됩니다. 시스템이 멋대로 삭제 안 합니다.
- `.processed/` 가 계속 쌓이면 디스크 차지. 사용자에게 한 달에 한 번 정리 안내.
- 시나리오 ②(STT)는 외부 도구 의존이라 별도 설치 필요.

---

## OS별 분기 — Windows 진행 방식

Windows에는 launchd `WatchPaths` 가 없으므로 **PowerShell `FileSystemWatcher`** 를 사용한 상주 스크립트 방식으로 갑니다.

### 폴더 + 인프라
```powershell
$watch = "{WATCH_FOLDER}"  # 예: $env:USERPROFILE + "\Documents\claude-inbox"
New-Item -ItemType Directory -Force -Path $watch | Out-Null
New-Item -ItemType Directory -Force -Path "$watch\.processed" | Out-Null
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\scripts\folder-watch\logs" | Out-Null
```

### watcher 스크립트 (`folder-watch.ps1`)
위치: `$env:USERPROFILE\.claude\scripts\folder-watch\folder-watch.ps1`

```powershell
$ErrorActionPreference = "Stop"
$WatchDir = "{WATCH_FOLDER}"
$ProcessedDir = Join-Path $WatchDir ".processed"
$LogDir = "$env:USERPROFILE\.claude\scripts\folder-watch\logs"

function Process-File($filePath) {
    $basename = Split-Path -LiteralPath $filePath -Leaf
    $log = Join-Path $LogDir "$(Get-Date -Format 'yyyy-MM-dd').log"
    "[$(Get-Date -Format 'HH:mm:ss')] Processing: $basename" | Out-File -Append -LiteralPath $log

    # WATCH_FOLDER · 파일명에 한글/공백이 있어도 안전하도록 모든 인자 quote + `--` 로 옵션 종료
    $prompt = "{SCENARIO_PROMPT} $filePath"
    claude --print --add-dir "$WatchDir" -- "$prompt" *>> "$log"

    $newName = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$basename"
    Move-Item -LiteralPath $filePath -Destination (Join-Path $ProcessedDir $newName)
}

# 시작 시 이미 있는 파일 한 번 정리
Get-ChildItem -Path $WatchDir -File | Where-Object { -not $_.Name.StartsWith('.') } | ForEach-Object {
    Process-File $_.FullName
}

# 실시간 watcher
$fsw = New-Object IO.FileSystemWatcher $WatchDir, "*" -Property @{
    IncludeSubdirectories = $false
    NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite'
}
Register-ObjectEvent $fsw Created -SourceIdentifier "FW-Created" -Action {
    Start-Sleep -Seconds 2  # 파일 쓰기 완료 대기
    if (Test-Path $Event.SourceEventArgs.FullPath) {
        Process-File $Event.SourceEventArgs.FullPath
    }
}
while ($true) { Start-Sleep -Seconds 60 }
```

### Task Scheduler 등록 (at logon)
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -File `"$env:USERPROFILE\.claude\scripts\folder-watch\folder-watch.ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName "FolderWatch" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName "FolderWatch"
```

### 검증
사용자 안내는 macOS와 동일. 로그 위치만 다름:
```powershell
Get-Content "$env:USERPROFILE\.claude\scripts\folder-watch\logs\$(Get-Date -Format 'yyyy-MM-dd').log" -Tail 30
```

### 트러블슈팅 (Windows)
| 증상 | 해결 |
|------|------|
| 파일 떨어뜨려도 반응 없음 | `Get-ScheduledTask FolderWatch | Get-ScheduledTaskInfo` 로 상태 확인 |
| `claude: 인식되지 않는 명령` | Claude Code 설치 경로가 PATH에 있는지 확인. 또는 ps1 안에서 절대경로 사용 |
| 파일이 잠겨서 못 옮김 | `Start-Sleep -Seconds 2` 값을 5~10초로 늘리기 |

---

## OS별 분기 — Linux 진행 방식

Linux에는 **systemd `.path` unit** 이 launchd `WatchPaths` 와 가장 비슷합니다.

### 폴더 + 인프라
```bash
WATCH="{WATCH_FOLDER}"
mkdir -p "$WATCH" "$WATCH/.processed" ~/.claude/scripts/folder-watch/logs
```

### watcher 스크립트 (`folder-watch.sh`)
macOS와 거의 동일. shell도 bash 그대로:
```bash
#!/bin/bash
set -euo pipefail
WATCH_DIR="{WATCH_FOLDER}"
PROCESSED_DIR="$WATCH_DIR/.processed"
LOG="$HOME/.claude/scripts/folder-watch/logs/$(date +%Y-%m-%d).log"

find "$WATCH_DIR" -maxdepth 1 -type f ! -name '.*' | while read -r FILE; do
    BASENAME=$(basename "$FILE")
    echo "[$(date '+%H:%M:%S')] Processing: $BASENAME" >> "$LOG"
    claude --print --add-dir "$WATCH_DIR" "{SCENARIO_PROMPT} $FILE" >> "$LOG" 2>&1
    mv "$FILE" "$PROCESSED_DIR/$(date +%Y%m%d-%H%M%S)-$BASENAME"
done
```

### systemd unit 짝
`~/.config/systemd/user/folder-watch.service`:
```ini
[Unit]
Description=Folder watch processor

[Service]
Type=oneshot
ExecStart=/bin/bash %h/.claude/scripts/folder-watch/folder-watch.sh
```

`~/.config/systemd/user/folder-watch.path`:
```ini
[Unit]
Description=Watch {WATCH_FOLDER} for new files

[Path]
PathChanged={WATCH_FOLDER}
TriggerLimitIntervalSec=5

[Install]
WantedBy=default.target
```

등록:
```bash
systemctl --user daemon-reload
systemctl --user enable --now folder-watch.path
loginctl enable-linger $(whoami)
```

### 트러블슈팅 (Linux)
| 증상 | 해결 |
|------|------|
| Path unit 안 발동 | `systemctl --user status folder-watch.path` 로 상태. `journalctl --user -u folder-watch.service` 로 실행 로그 |
| inotify 한계 | `/proc/sys/fs/inotify/max_user_watches` 확인. 보통 충분 |

---

## 운영 — 처리 완료 파일 정리

폴더 트리거가 처리 끝난 파일을 `.processed/` 로 옮깁니다. 누적되니 주기적 정리 권장.

### Windows
`templates/windows/cleanup-processed.ps1` 을 `~/.claude/scripts/cleanup-processed.ps1` 로 카피 후 월 1회 schtask:

```powershell
schtasks /Create /SC MONTHLY /D 1 /TN "AgentBootstrap-CleanupProcessed" `
  /TR "pwsh -File C:\Users\$env:USERNAME\.claude\scripts\cleanup-processed.ps1" /F
```

dry-run 으로 미리 확인:
```powershell
pwsh -File ~/.claude/scripts/cleanup-processed.ps1 -DryRun
```

### macOS / Linux
간단한 cron 으로 같은 효과:
```bash
# crontab -e — 매월 1일 03:00
0 3 1 * * find ~/.claude/scripts/folder-watch/*/.processed -type f -mtime +90 -delete
```
