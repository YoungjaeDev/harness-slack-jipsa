# .env 단일화 마이그레이션

직전 1차 수정에서 `settings.json env` 와 `.env` 의 중복을 `.env` 단일 출처로 통일했습니다.
기존 설치 사용자가 5분 안에 옮기는 절차입니다.

## 영향

- **이전**: `NOTION_API_TOKEN`, `NOTION_SESSION_DB`, `NOTION_DAILY_DB`, `SLACK_SESSION_WEBHOOK` 가 `~/.claude/settings.json` 의 `env` 섹션과 `.env` 양쪽에 있어 동기화 부담.
- **이후**: `.env` 만이 단일 출처. settings.json 의 env 섹션은 위 4개 비워도 동작.

## 마이그레이션 절차

### 1) settings.json 백업

```powershell
# Windows
Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.bak"
```

```bash
# macOS / Linux
cp ~/.claude/settings.json ~/.claude/settings.json.bak
```

### 2) .env 에 4개 변수 존재 확인

```powershell
# Windows
Get-Content "$env:USERPROFILE\.claude\secrets\slack-jipsa.env" |
  Select-String 'NOTION_API_TOKEN|NOTION_SESSION_DB|NOTION_DAILY_DB|SLACK_SESSION_WEBHOOK'
```

```bash
# macOS / Linux
grep -E 'NOTION_API_TOKEN|NOTION_SESSION_DB|NOTION_DAILY_DB|SLACK_SESSION_WEBHOOK' \
  ~/.claude/secrets/slack-jipsa.env
```

비어있는 항목은 settings.json 에서 값 복사 후 `.env` 에 추가.

### 3) settings.json 의 env 섹션에서 위 4개 키 제거

다른 env 항목은 보존. JSON 편집기로 열어서 그 4개만 삭제.

### 4) daemon 재시작

```powershell
# Windows
Stop-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
Start-ScheduledTask -TaskName AgentBootstrap-SlackDaemon
```

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/com.<user>.slack-jipsa.plist
launchctl load ~/Library/LaunchAgents/com.<user>.slack-jipsa.plist
```

```bash
# Linux
systemctl --user restart slack-jipsa.service
```

### 5) 검증

새 슬랙 메시지 1개 → 노션에 row 1개 생성되는지 확인.

## 문제 해결

| 증상 | 원인 / 해결 |
|------|-----------|
| `[daemon] WARN: BOT_USER_ID auth.test failed` | 토큰 권한 부족 또는 expired. `SLACK_BOT_TOKEN` 재발급 ([modules/security-token-rotation.md](security-token-rotation.md)) |
| 노션 row 안 만들어짐 | `~/.claude/scripts/slack-jipsa/logs/daemon.log.YYYY-MM-DD` 의 `notion_log_turn failed` 검색. 보통 `NOTION_SESSION_DB` 가 비어있거나 `.env` 에 token 누락 |
| daemon 부팅 fail | settings.json 의 다른 env (예: `PATH` 추가) 가 망가졌을 가능성. 백업 (`.bak`) 으로 복원 후 재시도 |
