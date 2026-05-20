# 보안 — Slack Bot Token 정기 교체

`SLACK_BOT_TOKEN` (`xoxb-...`) 은 채널 메시지 게시·읽기·반응 추가·멤버 목록 권한을 가집니다.
유출 시 채널 도청·스푸핑 가능. **3-6개월 주기 교체** 권장.

## 교체 절차 (5분)

### 1) Slack 앱 페이지 진입

https://api.slack.com/apps → 본인 앱 선택 → "OAuth & Permissions"

### 2) 새 토큰 발급

"Reinstall to Workspace" 클릭 → 권한 확인 → "Allow".
페이지 상단의 "Bot User OAuth Token" 의 새 `xoxb-...` 복사.

> 동일 앱에 reinstall 하면 기존 토큰은 즉시 무효화됩니다 — 외부에 노출된 토큰이 있다면 이 단계로 차단.

### 3) `.env` 의 SLACK_BOT_TOKEN 교체

```powershell
# Windows
notepad "$env:USERPROFILE\.claude\secrets\slack-jipsa.env"
```

```bash
# macOS / Linux
$EDITOR ~/.claude/secrets/slack-jipsa.env
```

`SLACK_BOT_TOKEN=` 라인의 값만 새 토큰으로 교체. 저장.

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

- 슬랙 채널에 메시지 1개 전송 → daemon 응답 확인.
- `~/.claude/scripts/slack-jipsa/logs/daemon.log.YYYY-MM-DD` 의 startup 라인 정상 출력.
- `~/.claude/scripts/slack-jipsa/audit/<date>.log` 에 새 invocation 기록 확인.

## 유출 의심 시 즉시 대응

1. **Slack 앱 페이지 → "Revoke Token"** — 토큰 즉시 무효화.
2. 위 절차 1-4 로 새 토큰 발급.
3. `~/.claude/scripts/slack-jipsa/audit/` 의 최근 7일 로그 검토 — 비정상 channel / session 호출 있는지.
4. 채널 멤버 monitor 의 로그 검토 (`logs/daemon.log` 에 `NEW CHANNEL MEMBERS` 검색) — 누가 join 했는지.

## 자동화 — 정기 알림 (옵션)

3개월마다 reminder 만 띄우는 schtask:

```powershell
# Windows
schtasks /Create /SC MONTHLY /MO 3 /TN "AgentBootstrap-TokenRotationReminder" `
  /TR 'msg %username% "Slack Bot Token 정기 교체 시기. modules/security-token-rotation.md 참고."' /F
```

```bash
# macOS / Linux — cron 으로 모듈 출력만 (직접 교체는 수동)
# crontab -e — 분기별 1일 09:00
0 9 1 */3 * echo "Slack Bot Token 교체 시기" | mail -s "Rotation reminder" $USER
```

## 관련 문서

- [.env 단일화 마이그레이션](migration-env-singularization.md) — `.env` 의 단일 출처 원칙
- [modules/01-slack-bridge.md](01-slack-bridge.md) — 슬랙 앱 셋업 본문
