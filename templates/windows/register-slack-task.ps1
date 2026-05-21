# Agent Bootstrap — Slack daemon 자동 시작 등록 (Task Scheduler)
# 실행:
#   글로벌:    powershell -ExecutionPolicy Bypass -File register-slack-task.ps1
#   프로젝트:  powershell -ExecutionPolicy Bypass -File register-slack-task.ps1 -ProjectId harness-slack-jipsa
# 관리자 권한 불필요 (current user task).
#
# 프로젝트 모드 시 Task name 에 `-{ProjectId}` suffix 가 붙어 글로벌 인스턴스와 공존 가능.

param(
    [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"

if ($ProjectId) {
    if ($ProjectId -notmatch '^[a-z][a-z0-9-]{0,30}$') {
        Write-Error "ProjectId '$ProjectId' 는 ^[a-z][a-z0-9-]{0,30}`$ 규칙 위반. SKILL.md Step 1.5 참고."
        exit 1
    }
    $Instance = "slack-jipsa-$ProjectId"
    $TaskName = "AgentBootstrap-SlackDaemon-$ProjectId"
} else {
    $Instance = "slack-jipsa"
    $TaskName = "AgentBootstrap-SlackDaemon"
}

$ScriptPath = Join-Path $env:USERPROFILE ".claude\scripts\$Instance\run-daemon.ps1"

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    Write-Error "Missing $ScriptPath — 모듈 1 run-daemon.ps1 카피 단계 먼저 진행 (Instance=$Instance)"
    exit 1
}

# SLACK_JIPSA_INSTANCE 를 Task 환경변수로 직접 주입할 방법이 없어 (PowerShell 5.x
# Register-ScheduledTask 에 Environment 옵션 없음), run-daemon.ps1 가 .env 의
# PROJECT_ID 를 보고 자체적으로 INSTANCE 를 계산하는 방식으로 처리.
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' 등록 완료 (Instance=$Instance). State=$((Get-ScheduledTask -TaskName $TaskName).State)"
